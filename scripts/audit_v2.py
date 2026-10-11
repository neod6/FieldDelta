import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results'/'v2'
manifest=json.loads((OUT/'manifest.json').read_text())
for relative,digest in manifest['source_hashes'].items():
    assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==digest, f'Source changed: {relative}'
result=json.loads((OUT/'evaluation.json').read_text())
assert result['data_split']=='DEVELOPMENT_ONLY'
assert len(result['pairs'])==21
for pair in result['pairs']:
    for kind,count in pair['counts'].items():
        assert count==sum(e['type']==kind for e in pair['events'])
    identities=[e['before_id'] for e in pair['events'] if e['before_id'] is not None]
    assert len(identities)==len(set(identities))
    observations=[e['after_id'] for e in pair['events'] if e['after_id'] is not None]
    assert len(observations)==len(set(observations))
    if not pair['registration']['reliable']:
        assert pair['counts']['MOVED']==0
registry=json.loads((OUT/'registry_proposal.json').read_text())
assert all(not e['confirmed'] for e in registry['objects'])
control=next(p for p in result['pairs'] if p['before']=='IMG_3377' and p['after']=='IMG_3378')
assert control['counts']==dict(ADDED=0,REMOVED=0,MOVED=0,UNCHANGED=8,UNKNOWN=1,NOT_OBSERVED=2)
summary=dict(status='PASS_ARTIFACT_INTEGRITY_NOT_VISION_ACCURACY',pairs=21,
             source_hashes_match=True,one_to_one_assignment=True,
             no_fabricated_enrollment_confirmation=True,
             original_v1_evidence_present=(ROOT/'results'/'user_batch'/'evaluation.json').is_file(),
             control_counts=control['counts'],decision='FIELDDELTA V2 STILL NOT RELIABLE')
(OUT/'audit.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
