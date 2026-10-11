import json
import math
from pathlib import Path
import uuid

import numpy as np
from scipy.optimize import linear_sum_assignment
from .registration import map_object, inside_roi, expected_in_view


def enrollment_candidates(scan, roi):
    return [dict(object_id=str(uuid.uuid5(uuid.NAMESPACE_URL,
                    scan['image_path']+'|'+json.dumps(o['normalized_bbox']))), display_name=o['label'],
                 confirmed=False, reference_crops=[o.get('crop_path')],
                 reference_embeddings=[o['embedding']], semantic_suggestions=o.get('semantic_suggestions',[o['label']]),
                 last_known_position=o['center'], last_seen_timestamp=scan['timestamp'], state='ENROLLMENT_CANDIDATE',
                 reference=o) for o in scan['objects'] if inside_roi(o['center'],roi)]


def save_registry(path, scan, roi, confirmed_ids=()):
    entries=enrollment_candidates(scan,roi)
    confirmed_ids=set(confirmed_ids)
    valid_ids={o['reference']['id'] for o in entries}
    if not confirmed_ids <= valid_ids:
        raise ValueError('Confirmation references unknown enrollment candidates')
    for entry in entries:
        entry['confirmed']=entry['reference']['id'] in confirmed_ids
    registry=dict(version=2, status='AWAITING_USER_CONFIRMATION' if not confirmed_ids else 'ENROLLED',
                  site_id='development_tabletop', roi=roi, reference_image=scan['image_path'],objects=entries)
    Path(path).write_text(json.dumps(registry,indent=2,allow_nan=False))
    return registry


def physical_cost(old,new):
    references=old.get('reference_embeddings',[old['embedding']])
    visual=float(np.clip(max(np.dot(vector,new['embedding']) for vector in references),-1,1))
    color=float(np.clip(np.sqrt(np.asarray(old['color'])*new['color']).sum(),0,1))
    center=new['registered_center']
    distance=math.dist(old['center'],center)
    a,b=old['normalized_bbox'],new['registered_bbox']
    aw,ah=max(a[2]-a[0],1e-6),max(a[3]-a[1],1e-6)
    bw,bh=max(b[2]-b[0],1e-6),max(b[3]-b[1],1e-6)
    size=min(abs(math.log(bw*bh/(aw*ah))),2)/2
    aspect=min(abs(math.log((bw/bh)/(aw/ah))),2)/2
    semantic=0 if old['label']==new['label'] else 1
    cost=.60*(1-visual)+.15*(1-color)+.12*min(distance/.35,1)+.07*size+.03*aspect+.03*semantic
    return dict(cost=cost, visual_similarity=visual,color_similarity=color,
                raw_displacement=math.dist(old['center'],new['center']),
                residual_displacement=distance,size_difference=size,aspect_difference=aspect,
                semantic_mismatch=bool(semantic))


def track(before,after,registration,roi, object_ids=None):
    old=[o for o in before if inside_roi(o['center'],roi)]
    new=[map_object(o,registration) for o in after]
    new=[o for o in new if inside_roi(o['registered_center'],roi)]
    n,m=len(old),len(new)
    costs=np.full((n+m,n+m),1e6)
    costs[:n,m:]=.16
    costs[n:,:m]=.16
    costs[n:,m:]=0
    evidence={}
    for i,a in enumerate(old):
        for j,b in enumerate(new):
            e=physical_cost(a,b)
            if e['visual_similarity'] >= .55 and e['cost'] < .32:
                costs[i,j]=e['cost']
                evidence[i,j]=e
    rows,cols=linear_sum_assignment(costs)
    events=[]
    matched_old,matched_new=set(),set()
    for i,j in zip(rows.tolist(),cols.tolist()):
        if (i,j) not in evidence:
            continue
        e=evidence[i,j]
        alternatives=[v['cost'] for (a,b),v in evidence.items() if (a==i or b==j) and (a,b)!=(i,j)]
        margin=min(alternatives,default=1)-e['cost']
        ambiguous=margin < .035 or e['visual_similarity'] < .65
        if not registration['reliable'] or ambiguous:
            kind='UNKNOWN'
            reason='REGISTRATION_UNCERTAIN' if not registration['reliable'] else 'AMBIGUOUS_IDENTITY'
        else:
            kind='MOVED' if e['residual_displacement'] > .045 else 'UNCHANGED'
            reason=None
        events.append(dict(type=kind, before_id=old[i]['id'],after_id=new[j]['id'],
                           object_id=(object_ids or {}).get(old[i]['id'],old[i]['id']),
                           before_label=old[i]['label'],after_label=new[j]['label'],
                           evidence=e,alternative_cost_margin=margin, reason=reason,
                           needs_review=kind=='UNKNOWN'))
        matched_old.add(i)
        matched_new.add(j)
    for i,a in enumerate(old):
        if i not in matched_old:
            visible=expected_in_view(a,registration)
            events.append(dict(type='NOT_OBSERVED',before_id=a['id'],after_id=None,
                               object_id=(object_ids or {}).get(a['id'],a['id']),before_label=a['label'],
                               reason='INSUFFICIENT_VISUAL_EVIDENCE' if visible else 'OUTSIDE_VIEW_OR_REGISTRATION_UNCERTAIN',
                               needs_review=True))
    for j,b in enumerate(new):
        if j not in matched_new:
            events.append(dict(type='UNKNOWN',before_id=None,after_id=b['id'],after_label=b['label'],
                               reason='NEW_ENROLLMENT_CANDIDATE_REQUIRES_CONFIRMATION', needs_review=True))
    # Two uncertain photos alone never prove absence. New candidates require enrollment.
    return dict(counts={k:sum(e['type']==k for e in events) for k in
                        ['ADDED','REMOVED','MOVED','UNCHANGED','UNKNOWN','NOT_OBSERVED']},
                events=events, roi_before_count=n,roi_after_count=m,
                state_policy='No automatic ADDED/REMOVED from unmatched detections; user confirmation or further visibility evidence required',
                requires_review=any(e['needs_review'] for e in events))


def confirm_registry(registry, names):
    """Explicit operator action, never detector-generated confirmation."""
    candidates={entry['reference']['id']:entry for entry in registry['objects']}
    if not names or not set(names) <= set(candidates):
        raise ValueError('Choose existing enrollment candidate IDs')
    for key,name in names.items():
        if not isinstance(name,str) or not name.strip() or len(name)>100:
            raise ValueError('A short non-empty display name is required')
        candidates[key].update(confirmed=True,display_name=name,state='UNCHANGED')
    registry['status']='ENROLLED'
    return registry


def observe_registry(registry, scan, registration):
    """Re-identify only operator-enrolled identities; keep registry IDs across scans."""
    entries=[e for e in registry['objects'] if e['confirmed']]
    if not entries:
        return dict(status='AWAITING_USER_CONFIRMATION',events=[],counts={})
    references=[{**e['reference'],'reference_embeddings':e['reference_embeddings']} for e in entries]
    ids={e['reference']['id']:e['object_id'] for e in entries}
    result=track(references,scan['objects'],registration,registry['roi'],ids)
    observations={o['id']:o for o in scan['objects']}
    by_id={e['object_id']:e for e in entries}
    for event in result['events']:
        if event.get('object_id') not in by_id:
            continue
        entry=by_id[event['object_id']]
        entry['state']=event['type']
        if event['type'] not in ('UNCHANGED','MOVED'):
            continue
        observed=map_object(observations[event['after_id']],registration)
        entry['last_known_position']=observed['registered_center']
        entry['last_seen_timestamp']=scan['timestamp']
        entry['reference_embeddings']=(entry['reference_embeddings']+[observed['embedding']])[-3:]
        entry['reference_crops']=(entry['reference_crops']+[observed.get('crop_path')])[-3:]
        # Geometry remains in the registry's baseline image frame, not current camera coordinates.
        entry['reference']={**observed,'id':entry['reference']['id'],
                            'center':observed['registered_center'],'normalized_bbox':observed['registered_bbox']}
    return dict(status='OBSERVED',**result)


def preview_registry(registry, scan, registration):
    """Diagnostic matching before enrollment; does not confirm or mutate identities."""
    entries=registry['objects']
    references=[{**e['reference'],'reference_embeddings':e['reference_embeddings']} for e in entries]
    ids={e['reference']['id']:e['object_id'] for e in entries}
    return dict(status='PROVISIONAL_IDENTITY_PREVIEW_NOT_CONFIRMED',
                **track(references,scan['objects'],registration,registry['roi'],ids))
