import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
sys.path.insert(0,str(ROOT))
from backend.v2.registration import load_image, register, warp_points
from backend.v2.tracking import track, save_registry, preview_registry
import numpy as np


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,allow_nan=False))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--registration-only',action='store_true')
    args=parser.parse_args()
    started=time.perf_counter()
    output=ROOT/'results'/'v2'
    config=json.loads((ROOT/'data'/'v2'/'site.json').read_text())
    paths=sorted((ROOT/'test_images'/'user_batch').glob('*.jpg'))
    images={p.stem:load_image(p) for p in paths}
    source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (ROOT/'backend'/'v2').glob('*.py')}
    manifest=dict(timestamp=datetime.now(timezone.utc).isoformat(),data_split='DEVELOPMENT_ONLY',
                  config=config,source_hashes=source_hashes,
                  image_hashes={p.stem:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                  baseline_v1_unchanged=True)
    save(output/'manifest.json',manifest)
    registrations={}
    for old,new in itertools.combinations(images,2):
        registrations[f'{old}__{new}']=register(images[old],images[new])
    save(output/'registration.json',registrations)
    reference=config['reference_image']
    ref_regs={name:register(images[reference],image) for name,image in images.items()}
    save(output/'roi_registration.json',ref_regs)
    original=json.loads((ROOT/'results'/'user_batch'/'evaluation.json').read_text())
    scans=original['scans']
    if not args.registration_only:
        from backend.v2.models import OpenDetector, InstanceEncoder
        import torch
        torch.set_num_threads(4)
        detector=OpenDetector(local_only=True)
        encoder=InstanceEncoder(local_only=True)
        scans={}
        for path in paths:
            name=path.stem
            cache=output/name/'scan.json'
            if cache.exists():
                scan=json.loads(cache.read_text())
            else:
                print(f'Detecting {name}',flush=True)
                image=images[name]
                detected=detector.detect(image,output/name)
                embedding_time=encoder.encode(image,detected['objects'],output/name)
                scan=dict(**detected,embedding_seconds=embedding_time,
                          image_path=str(path),width=image.width,height=image.height,
                          timestamp=datetime.now(timezone.utc).isoformat())
                save(cache,scan)
            scans[name]=scan
            print(name,[(o['label'],round(o['confidence'],2)) for o in scan['objects']],flush=True)
        save(output/'detector_comparison.json',dict(
            v1={n:dict(objects=s['objects'],latency_seconds=s['latency_seconds']) for n,s in original['scans'].items()},
            grounding_dino=scans))
        registry=save_registry(output/'registry_proposal.json',scans[reference],config['roi'])
        previews={name:preview_registry(registry,scan,ref_regs[name]) for name,scan in scans.items()}
        save(output/'registry_preview.json',dict(note='Stable provisional IDs, not user-confirmed enrollment',
                                                scans=previews))
    pairs=[]
    for old,new in itertools.combinations(images,2):
        reg=registrations[f'{old}__{new}']
        ref=ref_regs[old]
        roi=warp_points(config['roi'],np.linalg.inv(ref['matrix'])).tolist() if ref['matrix'] is not None else config['roi']
        if not ref['reliable']:
            reg={**reg,'reliable':False,'status':'REGISTRATION_UNCERTAIN','action':'RESCAN_RECOMMENDED'}
        result=track(scans[old]['objects'],scans[new]['objects'],reg,roi)
        pairs.append(dict(before=old,after=new,registration=reg,roi=roi,**result))
        print(old,new,result['counts'],flush=True)
    result=dict(data_split='DEVELOPMENT_ONLY',registration_only=args.registration_only,
                pairs=pairs,total_seconds=time.perf_counter()-started)
    save(output/('registration_ablation.json' if args.registration_only else 'evaluation.json'),result)


if __name__=='__main__':
    main()
