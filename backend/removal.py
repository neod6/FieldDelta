"""A narrowly gated verification layer; unmatched detections alone never mean removal."""
import numpy as np

from .v2.registration import expected_in_view,warp_points


def decide_removal(entry,registration,local_similarities,targeted,cloud):
    reasons=[]
    confirmed=bool(entry['confirmed'])
    if not confirmed:
        reasons.append('OBJECT_NOT_CONFIRMED')
    geometry_ok=bool(registration.get('reliable') and registration.get('matrix') is not None)
    coverage=geometry_ok and expected_in_view(entry['reference'],registration)
    if not geometry_ok:
        reasons.append('REGISTRATION_INSUFFICIENT_FOR_ABSENCE')
    if not coverage:
        reasons.append('TARGET_REGION_COVERAGE_NOT_CERTIFIED')
    best=max(local_similarities,default=-1)
    if best>=.75:
        reasons.append('STRONG_LOCAL_IDENTITY_MATCH')
    elif best>=.55:
        reasons.append('PLAUSIBLE_LOCAL_IDENTITY_MATCH')
    if not targeted.get('completed'):
        reasons.append('TARGETED_SEARCH_FAILED')
    elif targeted['objects']:
        reasons.append('TARGETED_SEARCH_FOUND_PLAUSIBLE_OBJECT_ELSEWHERE')
    verified=cloud.get('result',{})
    if cloud.get('status')!='completed':
        reasons.append('NO_INDEPENDENT_VISIBILITY_AND_ABSENCE_VERIFICATION')
    else:
        if verified.get('same_object_found') or verified.get('plausibly_moved_elsewhere'):
            reasons.append('CLOUD_FOUND_OR_SUSPECTS_RELOCATION')
        if not verified.get('region_visible') or not verified.get('region_unoccluded'):
            reasons.append('CLOUD_CANNOT_CERTIFY_VISIBLE_UNOCCLUDED_REGION')
        if not verified.get('absent_from_monitored_region') or verified.get('confidence',0)<.90:
            reasons.append('CLOUD_ABSENCE_EVIDENCE_INSUFFICIENT')
    return dict(object_id=entry['object_id'],label=entry['display_name'],
                type='NOT_OBSERVED' if reasons else 'REMOVED',accepted=not reasons,reasons=reasons,
                evidence=dict(confirmed=confirmed,alignment=registration,target_region_visible_geometrically=coverage,
                              max_local_dino_similarity=best,targeted_search=targeted,cloud=cloud,
                              removal_scope='Confirmed object absent from visible monitored region, not proof it left the entire site'))


def verify_objects(registry,descriptor,registration,detector,encoder,cloud_verify,output):
    from .v2.registration import load_image
    image=load_image(descriptor['image_path'])
    checks=[]
    for entry in registry['objects']:
        if not entry['confirmed'] or entry.get('state')=='REMOVED':
            continue
        refs=entry['reference_embeddings']
        similarities=[max(float(np.dot(ref,o['embedding'])) for ref in refs) for o in descriptor['objects']]
        # Identity search covers ALL detections, including objects outside the registered ROI.
        if max(similarities,default=-1)>=.75:
            continue
        prompts=list(dict.fromkeys([entry['reference']['label']]+entry.get('semantic_suggestions',[])))[:5]
        prompts=[p[:80] for p in prompts]
        targeted=dict(completed=False,objects=[],prompts=prompts,scope='entire_after_image')
        try:
            extracted=detector.detect(image,output/entry['object_id'],prompts=prompts)
            encoder.encode(image,extracted['objects'])
            targeted.update(completed=True,objects=[dict(label=o['label'],bbox=o['normalized_bbox'],
                detector_confidence=o['confidence'],dino_similarity=max(float(np.dot(ref,o['embedding'])) for ref in refs))
                for o in extracted['objects']],latency_seconds=extracted['latency_seconds'])
        except Exception as error:
            targeted['error_type']=type(error).__name__
        projected=None
        if registration.get('matrix') is not None:
            x1,y1,x2,y2=entry['reference']['normalized_bbox']
            points=warp_points([[x1,y1],[x2,y1],[x2,y2],[x1,y2]],np.linalg.inv(registration['matrix']))
            projected=[float(points[:,0].min()),float(points[:,1].min()),float(points[:,0].max()),float(points[:,1].max())]
        cloud=dict(status='unavailable')
        if cloud_verify is not None:
            try:
                cloud=dict(status='completed',**cloud_verify(registry['reference_image'],descriptor['image_path'],
                    dict(object_id=entry['object_id'],label=entry['display_name'],
                         before_box=entry.get('enrollment_reference',entry['reference'])['normalized_bbox'],
                         projected_after_box=projected,registration_reliable=registration['reliable'],
                         local_max_similarity=max(similarities,default=-1),targeted_search=targeted)))
            except Exception as error:
                cloud=dict(status='failed',error_type=type(error).__name__,
                           transport_attempts=getattr(error,'transport_attempts',[]))
        checks.append(decide_removal(entry,registration,similarities,targeted,cloud))
    return checks


def apply_checks(result,checks):
    value={**result,'events':[dict(e) for e in result.get('events',[])], 'controlled_removal':checks}
    for check in checks:
        if not check['accepted']:
            continue
        value['events']=[e for e in value['events'] if e.get('object_id')!=check['object_id']]
        value['events'].append(dict(object_id=check['object_id'],label=check['label'],type='REMOVED',
            local_type='NOT_OBSERVED',reason='CONTROLLED_REMOVAL_VERIFIED',evidence=check['evidence']))
    value['counts']={k.lower():sum(e['type']==k for e in value['events']) for k in ['ADDED','REMOVED','MOVED','UNCHANGED','UNCERTAIN']}
    return value
