import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.store import Store
from backend.app import create_app
from test_product import StubService


class MemoryTests(unittest.TestCase):
    def test_missing_mouse_persists_without_fabricated_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'memory.db'
            store=Store(path)
            baseline='memory-baseline'
            rescan='memory-rescan'
            store.create_scan(baseline,'loading-area','2026-10-11T20:40:06+00:00','fixture.jpg')
            store.finish(baseline,dict(objects=[dict(id='mouse-detection',label='mouse',confidence=.88,
                         normalized_bbox=[.6,.5,.8,.6],center=[.7,.55])]),
                         dict(counts=dict(added=0,removed=0,moved=0,unchanged=0,uncertain=1)),None,{'mouse-detection':'stable-mouse'})
            store.create_scan(rescan,'loading-area','2026-10-11T20:40:33+00:00','fixture.jpg')
            result=dict(events=[dict(object_id='stable-mouse',label='mouse',type='UNCERTAIN',local_type='NOT_OBSERVED')],
                        counts=dict(added=0,removed=0,moved=0,unchanged=0,uncertain=1))
            store.finish(rescan,dict(objects=[]),result,baseline,{})
            obj=store.memory('loading-area')[0]
            self.assertEqual(obj['status'],'NOT_OBSERVED')
            self.assertEqual(obj['presence'],'UNKNOWN')
            self.assertEqual(obj['last_seen_scan_id'],baseline)
            self.assertEqual(obj['last_seen'],'2026-10-11T20:40:06+00:00')
            self.assertFalse(store.observations(rescan)[0]['observed'])
            restarted=Store(path)
            self.assertEqual(restarted.memory('loading-area'),store.memory('loading-area'))
            with restarted.connection() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM change_events').fetchone()[0],1)
            self.assertEqual(restarted.memory('storage-a'),[])
            with TestClient(create_app(path,StubService)) as client:
                self.assertEqual(client.get('/').status_code,200)
                self.assertEqual(client.get('/dashboard/app.js').status_code,200)
                self.assertEqual(client.get('/scans/missing/detail').status_code,404)
                detail=client.get('/scans/'+rescan+'/detail').json()
                self.assertEqual(detail['previous_scan_id'],baseline)
                self.assertEqual(detail['result']['counts']['removed'],0)
                self.assertEqual(len(client.get('/sites/loading-area/state').json()['tracked_objects']),1)

    def test_additive_backfill_keeps_original_results_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'legacy.db'
            db=sqlite3.connect(path)
            db.executescript('''
                CREATE TABLE accounts(id TEXT PRIMARY KEY,name TEXT NOT NULL,is_demo INTEGER DEFAULT 1);
                CREATE TABLE sites(id TEXT PRIMARY KEY,account_id TEXT,name TEXT,description TEXT DEFAULT '');
                CREATE TABLE scans(id TEXT PRIMARY KEY,site_id TEXT,timestamp TEXT,created_at TEXT,image_path TEXT,scan_type TEXT,processing_status TEXT,error TEXT,descriptor_json TEXT,result_json TEXT,previous_scan_id TEXT);
                CREATE TABLE scene_objects(id TEXT PRIMARY KEY,scan_id TEXT,stable_id TEXT,label TEXT,confidence REAL,bbox_json TEXT,position_json TEXT,matching_confidence REAL,verification_status TEXT);
                CREATE TABLE change_events(id TEXT PRIMARY KEY,site_id TEXT,previous_scan_id TEXT,current_scan_id TEXT,type TEXT,object_json TEXT,timestamp TEXT);
            ''')
            result=json.dumps(dict(counts=dict(added=0,removed=0,moved=0,unchanged=0,uncertain=1),events=[]))
            db.execute('INSERT INTO accounts VALUES(?,?,?)',('demo-warehouse','Demo Warehouse',1))
            db.execute('INSERT INTO sites VALUES(?,?,?,?)',('loading-area','demo-warehouse','Loading Area',''))
            db.execute('INSERT INTO scans VALUES(?,?,?,?,?,?,?,?,?,?,?)',('legacy','loading-area','2026-10-11T20:00:00Z','2026-10-11T20:00:00Z','fixture.jpg','baseline','complete',None,'{}',result,None))
            db.execute('INSERT INTO scene_objects VALUES(?,?,?,?,?,?,?,?,?)',('legacy-object','legacy','stable','mouse',.88,'[0,0,1,1]','[0.5,0.5]',None,'PROVISIONAL'))
            db.commit(); db.close()
            with patch.object(Store,'registry',return_value=dict(status='AWAITING_USER_CONFIRMATION',objects=[])):
                store=Store(path)
                Store(path)
            self.assertEqual(store.scan('legacy')['result_json'],result)
            self.assertEqual(len(store.observations('legacy')),1)
            self.assertEqual(len(store.memory('loading-area')),1)
            self.assertEqual(len(store.scans('loading-area')),1)


if __name__=='__main__':
    unittest.main()
