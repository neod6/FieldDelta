import json
import os
from pathlib import Path
import uuid

from .cloud import compare_cloud,compact_evidence,settings
from .hybrid import fuse

ROOT=Path(__file__).resolve().parents[1]
ROI=[[0,0.28],[1,0.28],[1,1],[0,1]]


class ScanService:
    def __init__(self,store):
        self.store=store
        self.detector=None
        self.encoder=None

    def process(self,scan_id):
        from .v2.registration import load_image,register,warp_points
        from .v2.tracking import track,save_registry,observe_registry
        scan=self.store.scan(scan_id)
        try:
            self.store.status(scan_id,'processing')
            os.environ['HF_HUB_OFFLINE']='1'
            os.environ['TRANSFORMERS_OFFLINE']='1'
            from .v2.models import OpenDetector,InstanceEncoder
            import torch
            torch.set_num_threads(4)
            if self.detector is None:
                self.detector=OpenDetector(local_only=True)
                self.encoder=InstanceEncoder(local_only=True)
            image=load_image(scan['image_path'])
            directory=ROOT/'results'/'product_scans'/scan_id
            extracted=self.detector.detect(image,directory)
            extracted['embedding_seconds']=self.encoder.encode(image,extracted['objects'],directory)
            # Scan-local IDs are unique across the database, not just per image.
            for obj in extracted['objects']:
                obj['id']=scan_id+'_'+obj['id']
            descriptor=dict(**extracted,image_path=scan['image_path'],timestamp=scan['timestamp'])
            previous=self.store.latest(scan['site_id'],exclude=scan_id)
            ids={o['id']:str(uuid.uuid4()) for o in descriptor['objects']}
            registry_path=self.store.registry_path(scan['site_id'],scan['session_id'])
            registry_path.parent.mkdir(parents=True,exist_ok=True)
            if previous is None:
                registry=save_registry(registry_path,descriptor,ROI)
                ids.update({e['reference']['id']:e['object_id'] for e in registry['objects']})
                result=dict(mode='baseline_candidates',counts=dict(added=0,removed=0,moved=0,unchanged=0,uncertain=len(registry['objects'])),
                            events=[],warning='Experimental baseline saved. Candidate objects await enrollment confirmation.',
                            cloud_status='not_needed_for_baseline')
            else:
                before=json.loads(previous['descriptor_json'])
                registration=register(load_image(previous['image_path']),image)
                import numpy as np
                registry=self.store.load_registry(scan['site_id'],scan['session_id'])
                roi_registration=register(load_image(registry['reference_image']),load_image(previous['image_path']))
                roi=warp_points(registry['roi'],np.linalg.inv(roi_registration['matrix'])).tolist() if roi_registration['matrix'] is not None else registry['roi']
                if not roi_registration['reliable']:
                    registration={**registration,'reliable':False,'status':'ROI_REGISTRATION_UNCERTAIN'}
                old_ids={o['id']:o['stable_id'] for o in self.store.objects(previous['id'])}
                local=track(before['objects'],descriptor['objects'],registration,roi,old_ids)
                for e in local['events']:
                    if e.get('after_id') and e.get('before_id'):
                        ids[e['after_id']]=old_ids[e['before_id']]
                config=settings()
                if config['enabled'] and config['key']:
                    self.store.status(scan_id,'cloud_processing')
                    try:
                        cloud=compare_cloud(previous['image_path'],scan['image_path'],
                                            compact_evidence(before,descriptor,local,registration,roi,old_ids))
                        result=fuse(local,cloud['result'],before,descriptor,registration)
                        result.update(cloud_status='completed',cloud_usage=cloud['usage'],cloud_latency_seconds=cloud['latency_seconds'])
                        (directory/'cloud.json').write_text(json.dumps(cloud,indent=2))
                    except Exception as error:
                        result=self.uncertain_local(local,'Cloud verification failed: '+type(error).__name__)
                        metadata=getattr(error,'cloud_metadata',{})
                        (directory/'cloud_error.json').write_text(json.dumps(dict(error_type=type(error).__name__,**metadata),indent=2))
                else:
                    result=self.uncertain_local(local,'Cloud unavailable or disabled; local observations are unverified')
                result['registration']=registration
                result['local_counts']=local['counts']
                (directory/'local.json').write_text(json.dumps(local,indent=2))
                if registry_path.exists():
                    registry=self.store.load_registry(scan['site_id'],scan['session_id'])
                    base_reg=register(load_image(registry['reference_image']),image)
                    checks=self.removal_checks(registry,descriptor,base_reg,directory/'removal_search')
                    if checks:
                        from .removal import apply_checks
                        result=apply_checks(result,checks)
                    registry_result=observe_registry(registry,descriptor,base_reg)
                    for event in registry_result.get('events',[]):
                        if event.get('after_id') and event.get('object_id') and event['type'] in ('MOVED','UNCHANGED'):
                            ids[event['after_id']]=event['object_id']
                    for check in checks:
                        if check['accepted']:
                            next(e for e in registry['objects'] if e['object_id']==check['object_id'])['state']='REMOVED'
                    registry_path.write_text(json.dumps(registry,indent=2))
                    result['registry_status']=registry_result['status']
            self.store.finish(scan_id,descriptor,result,previous['id'] if previous else None,ids)
        except Exception as error:
            self.store.status(scan_id,'failed','Processing failed: '+type(error).__name__)

    def removal_checks(self,registry,descriptor,registration,directory):
        from .removal import verify_objects
        from .removal_cloud import verify_absence
        config=settings()
        return verify_objects(registry,descriptor,registration,self.detector,self.encoder,
                              verify_absence if config['enabled'] and config['key'] else None,directory)

    def review_removal(self,scan_id):
        from .v2.registration import load_image,register
        from .v2.models import OpenDetector,InstanceEncoder
        import torch
        try:
            torch.set_num_threads(4)
            os.environ['HF_HUB_OFFLINE']='1'
            os.environ['TRANSFORMERS_OFFLINE']='1'
            if self.detector is None:
                self.detector=OpenDetector(local_only=True)
                self.encoder=InstanceEncoder(local_only=True)
            scan=self.store.scan(scan_id)
            registry=self.store.load_registry(scan['site_id'],scan['session_id'])
            descriptor=json.loads(scan['descriptor_json'])
            registration=register(load_image(registry['reference_image']),load_image(scan['image_path']))
            checks=self.removal_checks(registry,descriptor,registration,ROOT/'results'/'product_scans'/scan_id/'removal_search')
            self.store.save_removal_review(scan_id,checks)
        except Exception as error:
            self.store.save_removal_review(scan_id,[],type(error).__name__)

    @staticmethod
    def uncertain_local(local,reason):
        return dict(mode='local_unverified',cloud_status='unavailable',warning=reason,
                    counts=dict(added=0,removed=0,moved=0,unchanged=0,uncertain=len(local['events'])),
                    events=[dict(object_id=e.get('object_id') or str(uuid.uuid4()),type='UNCERTAIN',
                                 label=e.get('after_label',e.get('before_label','Unknown')),
                                 local_type=e['type'],reason=reason) for e in local['events']])
