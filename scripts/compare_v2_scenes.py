"""Frozen initial fresh-photo evaluation. Never modifies model parameters."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.v2.registration import load_image,register
from backend.v2.models import OpenDetector,InstanceEncoder
from backend.v2.tracking import track,save_registry
import torch


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--before',type=Path,required=True)
    parser.add_argument('--after',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--roi',type=float,nargs=4,required=True,metavar=('X1','Y1','X2','Y2'),
                        help='Declare baseline inspection rectangle, normalized to [0,1], before running')
    args=parser.parse_args()
    if args.output.exists():
        parser.error('Use a new output directory: initial validation evidence must not be overwritten')
    x1,y1,x2,y2=args.roi
    if not (0<=x1<x2<=1 and 0<=y1<y2<=1):
        parser.error('Invalid ROI')
    for path in (args.before,args.after):
        if not path.is_file():
            parser.error(f'Missing photo: {path}')
    args.output.mkdir(parents=True)
    started=time.perf_counter()
    images=[load_image(args.before),load_image(args.after)]
    registration=register(*images)
    torch.set_num_threads(4)
    detector,encoder=OpenDetector(local_only=True),InstanceEncoder(local_only=True)
    scans=[]
    for name,path,image in zip(['before','after'],[args.before,args.after],images):
        scan=detector.detect(image,args.output/name)
        scan['embedding_seconds']=encoder.encode(image,scan['objects'],args.output/name)
        scan.update(image_path=str(path.resolve()),timestamp=datetime.now(timezone.utc).isoformat())
        scans.append(scan)
    roi=[[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
    result=dict(data_split='FRESH_VALIDATION_INITIAL_UNTUNED',
                registration=registration,roi=roi,before=scans[0],after=scans[1],
                total_seconds=time.perf_counter()-started,
                source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (ROOT/'backend'/'v2').glob('*.py')},
                **track(scans[0]['objects'],scans[1]['objects'],registration,roi))
    (args.output/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    save_registry(args.output/'registry_proposal.json',scans[0],roi)
    print(json.dumps(dict(counts=result['counts'],registration_status=registration['status'],
                         latency_seconds=result['total_seconds']),indent=2))


if __name__=='__main__':
    main()
