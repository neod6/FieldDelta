import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.cloud import compare_cloud,compact_evidence,settings,PROMPT,Comparison
from backend.hybrid import fuse

OUT=ROOT/'results'/'luminal_development'


def run_pair(pair):
    name=pair['before']+'__'+pair['after']
    before=json.loads((ROOT/'results'/'v2'/pair['before']/'scan.json').read_text())
    after=json.loads((ROOT/'results'/'v2'/pair['after']/'scan.json').read_text())
    paths=[ROOT/'test_images'/'user_batch'/f'{n}.jpg' for n in [pair['before'],pair['after']]]
    directory=OUT/name
    directory.mkdir(parents=True,exist_ok=True)
    result=dict(before=pair['before'],after=pair['after'],data_split='DEVELOPMENT_ONLY',local_counts=pair['counts'])
    registry=json.loads((ROOT/'results'/'v2'/'registry_proposal.json').read_text())
    ids={e['reference']['id']:e['object_id'] for e in registry['objects']} if pair['before']=='IMG_3377' else {}
    context=compact_evidence(before,after,pair,pair['registration'],pair['roi'],ids)
    for mode,ctx in [('cloud_only',{'inspection_roi_in_before_coordinates':pair['roi']}),('cloud_with_local_evidence',context)]:
        cache=directory/f'{mode}.json'
        fingerprint=hashlib.sha256(('luminal-json-object-client-schema-low-thinking-disabled-3500-v3'+PROMPT+settings()['base_url']+settings()['model']+json.dumps(Comparison.model_json_schema(),sort_keys=True)+json.dumps(ctx,sort_keys=True)).encode()
                                   +paths[0].read_bytes()+paths[1].read_bytes()).hexdigest()
        try:
            if cache.exists() and json.loads(cache.read_text()).get('fingerprint')==fingerprint:
                response=json.loads(cache.read_text())
            else:
                response={**compare_cloud(*paths,context=ctx),'fingerprint':fingerprint}
                cache.write_text(json.dumps(response,indent=2))
            result[mode]=response
        except Exception as error:
            # Do not print raw SDK exceptions, headers, API keys or request bodies.
            result[mode]=dict(error_type=type(error).__name__,http_status=getattr(error,'status_code',None),
                              error_code=getattr(error,'code',None),transport_attempts=getattr(error,'transport_attempts',[]))
            result[mode].update(getattr(error,'cloud_metadata',{}))
            break
    if 'cloud_with_local_evidence' in result and 'result' in result['cloud_with_local_evidence']:
        result['hybrid']=fuse(pair,result['cloud_with_local_evidence']['result'],before,after,pair['registration'])
    current=directory/'comparison.json'
    if current.exists():
        with (directory/'comparison_history.jsonl').open('a') as history:
            history.write(json.dumps(json.loads(current.read_text()))+'\n')
    current.write_text(json.dumps(result,indent=2))
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--limit',type=int,default=21)
    parser.add_argument('--pairs',nargs='+',help='Development pairs, e.g. IMG_3377__IMG_3378')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    pairs=json.loads((ROOT/'results'/'v2'/'evaluation.json').read_text())['pairs']
    if args.pairs:
        pairs=[p for p in pairs if p['before']+'__'+p['after'] in args.pairs]
    pairs.sort(key=lambda p:(0 if (p['before'],p['after'])==('IMG_3377','IMG_3378') else 1,p['before'],p['after']))
    records=[]
    with ThreadPoolExecutor(max_workers=1) as pool:
        futures=[pool.submit(run_pair,p) for p in pairs[:args.limit]]
        for future in as_completed(futures):
            result=future.result()
            records.append(result)
            print(result['before'],result['after'],
                  result.get('hybrid',{}).get('counts',{}),
                  {m:r['error_type'] for m,r in result.items() if isinstance(r,dict) and 'error_type' in r},flush=True)
            (OUT/'summary.json').write_text(json.dumps(dict(data_split='DEVELOPMENT_ONLY',records=records),indent=2))
    failures=sum(any(isinstance(v,dict) and 'error_type' in v for v in r.values()) for r in records)
    print(f'Pairs complete: {len(records)}, failed pairs: {failures}',flush=True)
    return 1 if failures else 0


if __name__=='__main__':
    sys.exit(main())
