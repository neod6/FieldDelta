from scipy.optimize import linear_sum_assignment
import numpy as np


def iou(a,b):
    if a is None or b is None:
        return 0.
    area=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    return area/max((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-area,1e-8)


def fuse(local,cloud,before,after,registration):
    """Accept only sufficiently strong independent instance-level agreement."""
    old={o['id']:o for o in before['objects']}
    new={o['id']:o for o in after['objects']}
    matches=cloud['matches']
    events=local['events']
    scores=np.zeros((len(matches),len(events)))
    for i,c in enumerate(matches):
        for j,e in enumerate(events):
            a=old.get(e.get('before_id'),{}).get('normalized_bbox')
            b=new.get(e.get('after_id'),{}).get('normalized_bbox')
            if c['before_box'] is not None and c['after_box'] is not None and a is not None and b is not None:
                scores[i,j]=min(iou(c['before_box'],a),iou(c['after_box'],b))
            elif c['before_box'] is not None and c['after_box'] is None and a is not None and b is None:
                scores[i,j]=iou(c['before_box'],a)
            elif c['before_box'] is None and c['after_box'] is not None and a is None and b is not None:
                scores[i,j]=iou(c['after_box'],b)
    assignments={}
    if scores.size:
        rows,cols=linear_sum_assignment(scores,maximize=True)
        assignments={i:j for i,j in zip(rows.tolist(),cols.tolist()) if scores[i,j]>=.35}
    cloud_types={key:kind.upper() for kind in ['added','removed','moved','unchanged'] for key in cloud[kind]}
    decisions=[]
    used=set()
    for i,c in enumerate(matches):
        kind=cloud_types.get(c['object_id'],'UNCERTAIN')
        local_event=events[assignments[i]] if i in assignments else None
        accepted=False
        if local_event:
            used.add(assignments[i])
            evidence=local_event.get('evidence',{})
            accepted=bool(kind==local_event['type'] and kind in ('MOVED','UNCHANGED')
                          and c['confidence']>=.80 and evidence.get('visual_similarity',0)>=.75
                          and local_event.get('alternative_cost_margin',0)>=.035 and registration['reliable'])
        decisions.append(dict(object_id=(local_event.get('object_id') or c['object_id']) if local_event else 'cloud:'+c['object_id'],
                              label=c['label'],type=kind if accepted else 'UNCERTAIN',
                              cloud_type=kind,local_type=local_event['type'] if local_event else None,
                              reason='HIGH_CONFIDENCE_AGREEMENT' if accepted else 'DISAGREEMENT_OR_INSUFFICIENT_INDEPENDENT_EVIDENCE',
                              before_box=c['before_box'],after_box=c['after_box'],confidence=c['confidence']))
    for j,e in enumerate(events):
        if j not in used:
            decisions.append(dict(object_id=e.get('object_id') or 'local_'+str(j),
                                  label=e.get('after_label',e.get('before_label','Unknown')),
                                  type='UNCERTAIN',cloud_type=None,local_type=e['type'],
                                  reason='NO_CLOUD_CORROBORATION'))
    return dict(mode='hybrid_experimental',events=decisions,
                counts={k.lower():sum(e['type']==k for e in decisions) for k in ['ADDED','REMOVED','MOVED','UNCHANGED','UNCERTAIN']},
                warning='Experimental: agreement is not ground truth; uncertain states require review.')
