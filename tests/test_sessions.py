import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from backend.app import create_app
from backend.cloud import parse_comparison
from backend.store import Store
import test_product


class SessionService:
    """Transport fixture; no claim of model accuracy."""
    def __init__(self,store):
        self.store=store

    def process(self,scan_id):
        scan=self.store.scan(scan_id)
        previous=self.store.latest(scan['site_id'],exclude=scan_id)
        obj=dict(id=scan_id+'-mouse',label='Mouse',confidence=.88,normalized_bbox=[.1,.1,.2,.2],center=[.15,.15])
        self.store.finish(scan_id,dict(objects=[obj]),dict(mode='fixture',events=[],counts=dict(added=0,removed=0,moved=0,unchanged=0,uncertain=1)),
                          previous['id'] if previous else None,{obj['id']:scan['session_id']+'-mouse'})


class SessionTests(unittest.TestCase):
    def test_manual_new_baseline_history_scope_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.db'
            stream=io.BytesIO(); Image.new('RGB',(16,16)).save(stream,format='JPEG')
            fields=dict(account_id='demo-warehouse',site_id='storage-a',timestamp='2026-10-11T21:30:00Z')
            with TestClient(create_app(path,SessionService)) as client:
                def upload(**extra):
                    response=client.post('/sites/storage-a/scan',data={**fields,**extra},files={'image':('fixture.jpg',stream.getvalue(),'image/jpeg')})
                    self.assertEqual(response.status_code,202,response.text)
                    for _ in range(100):
                        scan=client.get('/scans/'+response.json()['id']).json()
                        if scan['processing_status']=='complete':
                            return scan
                        time.sleep(.01)
                    self.fail('Fixture did not complete')
                first=upload(new_inspection='true')
                second=upload(session_id=first['session_id'])
                third=upload(new_inspection='true',session_id=first['session_id'])
                fourth=upload(session_id=third['session_id'])
                self.assertEqual(first['scan_type'],'baseline')
                self.assertEqual(third['scan_type'],'baseline')
                self.assertIsNone(third['previous_scan_id'])
                self.assertEqual(second['previous_scan_id'],first['id'])
                self.assertEqual(fourth['previous_scan_id'],third['id'])
                self.assertNotEqual(first['session_id'],third['session_id'])
                state=client.get('/sites/storage-a/state').json()
                self.assertEqual(len(state['tracked_objects']),1)
                self.assertEqual(state['tracked_objects'][0]['last_seen_scan_id'],fourth['id'])
                self.assertEqual(len(state['sessions']),2)
                stale=client.post('/sites/storage-a/scan',data={**fields,'session_id':first['session_id']},files={'image':('fixture.jpg',stream.getvalue(),'image/jpeg')})
                self.assertEqual(stale.status_code,409)
            store=Store(path)
            self.assertEqual(len(store.scans('storage-a')),4)
            self.assertEqual(store.active_session('storage-a')['id'],third['session_id'])
            self.assertEqual(len(store.memory('storage-a',first['session_id'])),1)
            self.assertNotEqual(store.registry_path('storage-a',first['session_id']),store.registry_path('storage-a',third['session_id']))
            with self.assertRaises(ValueError):
                store.finish(fourth['id'],dict(objects=[]),{},first['id'],{})

    def test_pending_baseline_and_processing_order_are_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'test.db')
            store.create_scan('a','storage-a','2026-10-11T21:30:00Z','fixture.jpg')
            with self.assertRaises(ValueError):
                store.create_scan('b','storage-a','2026-10-11T21:31:00Z','fixture.jpg')
            store.create_scan('new','storage-a','2026-10-11T21:32:00Z','fixture.jpg',new_inspection=True)
            store.finish('a',dict(objects=[]),{},None,{})
            self.assertIsNone(store.latest('storage-a'))
            self.assertIsNone(store.latest('storage-a',exclude='new'))

    def test_possibly_missing_is_presentation_only_and_has_no_fake_confidence(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'test.db')
            store.create_scan('a','storage-a','2026-10-11T21:30:00Z','fixture.jpg')
            store.finish('a',dict(objects=[]),{},None,{})
            store.create_scan('b','storage-a','2026-10-11T21:31:00Z','fixture.jpg')
            check=dict(object_id='mouse',label='Mouse',accepted=False,type='NOT_OBSERVED',evidence=dict(confirmed=True,max_local_dino_similarity=.3))
            store.finish('b',dict(objects=[]),dict(events=[],controlled_removal=[check],counts=dict(removed=0)),'a',{})
            result=store.public_scan(store.scan('b'))
            self.assertEqual(result['object_results'],[dict(object_id='mouse',label='Mouse',status='POSSIBLY_MISSING',reason='Needs review')])
            self.assertEqual(result['result']['counts']['removed'],0)
            original=store.scan('b')['result_json']
            store.save_cloud_review('b',dict(events=[],controlled_removal=[check],counts=dict(removed=0)),dict(http_status=200))
            restarted=Store(store.path)
            self.assertEqual(restarted.scan('b')['result_json'],original)
            self.assertEqual(restarted.cloud_evidence('b')['http_status'],200)
            self.assertEqual(restarted.public_scan(restarted.scan('b'))['object_results'][0]['status'],'POSSIBLY_MISSING')
            with store.connection() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM change_events WHERE type="REMOVED"').fetchone()[0],0)

    def test_cloud_normalization_does_not_repair_semantics(self):
        data=test_product.ProductTests().comparison()
        data['unchanged']=[dict(object_id='can')]
        data['matches'][0]['before_box']=dict(x1=.1,y1=.1,x2=.2,y2=.2)
        parsed,changes=parse_comparison('```json\n'+json.dumps(data)+'\n```')
        self.assertEqual(parsed.unchanged,['can'])
        self.assertEqual(len(changes),3)
        data['moved']=['can']
        with self.assertRaises(ValidationError):
            parse_comparison(json.dumps(data))
        del data['moved']; del data['matches'][0]['confidence']
        with self.assertRaises(ValidationError):
            parse_comparison(json.dumps(data))
        with self.assertRaises(ValidationError):
            parse_comparison('{broken json')


if __name__=='__main__':
    unittest.main()
