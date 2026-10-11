"""Replay actual captures in a provenance-labelled inspection; never overwrite history."""
import argparse
import json
from pathlib import Path
import sys
import uuid

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app import app
from backend.images import normalize_upload
from backend.service import ScanService

OUT=ROOT/'results'/'landscape_reprocessing'


def replay(source_id,orientation,new_inspection):
    store=app.state.store
    source=store.scan(source_id)
    if not source or source['processing_status']!='complete':
        raise ValueError('Choose a completed original scan')
    sid=str(uuid.uuid4())
    path=ROOT/'uploads'/source['site_id']/(sid+'.jpg')
    raw=Path(source['image_path']).read_bytes()
    with Image.open(source['image_path']) as image:
        photo,metadata=normalize_upload(image,orientation)
    photo.thumbnail((2048,2048))
    photo.save(path,quality=92)
    path.with_suffix('.original').write_bytes(raw)
    metadata.update(source_scan_id=source_id,orientation_source='operator_verified_legacy_repair',
                    note='Original capture lost EXIF; direction verified visually, not inferred from aspect ratio.')
    path.with_suffix('.upload.json').write_text(json.dumps(metadata,indent=2))
    store.create_scan(sid,source['site_id'],source['timestamp'],path,new_inspection=new_inspection)
    ScanService(store).process(sid)
    scan=store.scan(sid)
    if scan['processing_status']!='complete':
        raise RuntimeError(scan['error'] or 'Reprocessing failed')
    with store.connection() as db:
        result=json.loads(scan['result_json'])
        result['reprocessing']=dict(source_scan_id=source_id,source_session_id=source['session_id'],
                                   reason='LANDSCAPE_ORIENTATION_REPAIR',orientation=metadata,
                                   actual_new_capture=False)
        db.execute('UPDATE scans SET result_json=? WHERE id=?',(json.dumps(result),sid))
    report=dict(scan=store.public_scan(store.scan(sid)),orientation=metadata,
                registry=store.registry(source['site_id']),raw_detections=store.objects(sid))
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/(source['scan_type']+'.json')).write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(reprocessed_scan_id=sid,source_scan_id=source_id,
                         scan_type=source['scan_type'],counts=result.get('counts'),
                         cloud_status=result.get('cloud_status'),normalized_size=metadata['normalized_size'],
                         candidates=[dict(id=o['object_id'],label=o['display_name'],bbox=o['bbox']) for o in report['registry']['objects']]),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('source_scan_id')
    parser.add_argument('--orientation',type=int,choices=range(1,9),required=True)
    parser.add_argument('--baseline',action='store_true')
    args=parser.parse_args()
    if not args.baseline:
        baseline=json.loads((OUT/'baseline.json').read_text())['scan']
        source=app.state.store.scan(args.source_scan_id)
        if source['previous_scan_id']!=baseline['result']['reprocessing']['source_scan_id']:
            raise ValueError('Source pair is not in the same history chain')
        if app.state.store.active_session(source['site_id'])['id']!=baseline['session_id']:
            raise ValueError('Active inspection changed; do not mix replay sessions')
    replay(args.source_scan_id,args.orientation,args.baseline)
