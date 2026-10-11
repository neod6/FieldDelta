import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.removal import decide_removal,verify_objects
from backend.store import Store
from PIL import Image


class ControlledRemovalTests(unittest.TestCase):
    def test_secondary_search_covers_entire_image_and_vetoes_relocation(self):
        with tempfile.TemporaryDirectory() as directory:
            image=Path(directory)/'fixture.jpg'
            Image.new('RGB',(64,64),'white').save(image)
            entry={**self.evidence(), 'reference_embeddings':[[1.,0.]],
                   'reference':dict(label='mouse',normalized_bbox=[.4,.4,.5,.5]),'semantic_suggestions':['mouse']}
            registry=dict(reference_image=str(image),objects=[entry])
            from unittest.mock import MagicMock
            detector=MagicMock()
            detector.detect.return_value=dict(objects=[],latency_seconds=.01)
            encoder=MagicMock()
            cloud=MagicMock(return_value=dict(result=self.cloud()['result']))
            checks=verify_objects(registry,dict(image_path=str(image),objects=[]),self.registration(),detector,encoder,cloud,Path(directory))
            self.assertTrue(checks[0]['accepted'])
            self.assertEqual(detector.detect.call_args.args[0].size,(64,64))
            self.assertEqual(detector.detect.call_args.kwargs['prompts'],['mouse'])
            detector.detect.return_value['objects']=[dict(label='mouse',normalized_bbox=[.8,.8,.9,.9],confidence=.9,embedding=[1.,0.])]
            checks=verify_objects(registry,dict(image_path=str(image),objects=[]),self.registration(),detector,encoder,cloud,Path(directory))
            self.assertFalse(checks[0]['accepted'])
            self.assertIn('TARGETED_SEARCH_FOUND_PLAUSIBLE_OBJECT_ELSEWHERE',checks[0]['reasons'])

    def evidence(self):
        return dict(object_id='mouse-stable',display_name='Mouse',confirmed=True,
                    reference=dict(normalized_bbox=[.4,.4,.5,.5]))

    def registration(self):
        return dict(reliable=True,matrix=[[1,0,0],[0,1,0],[0,0,1]])

    def cloud(self):
        return dict(status='completed',result=dict(same_object_found=False,region_visible=True,
                    region_unoccluded=True,absent_from_monitored_region=True,plausibly_moved_elsewhere=False,
                    confidence=.95,evidence='Synthetic unit-test absence evidence'))

    def decide(self,entry=None,registration=None,similarities=None,targeted=None,cloud=None):
        return decide_removal(entry or self.evidence(),registration or self.registration(),
                              similarities if similarities is not None else [.1],
                              targeted or dict(completed=True,objects=[]),cloud or self.cloud())

    def test_all_gates_required(self):
        self.assertTrue(self.decide()['accepted'])
        entry=self.evidence(); entry['confirmed']=False
        self.assertFalse(self.decide(entry=entry)['accepted'])
        reg=self.registration(); reg['reliable']=False
        self.assertFalse(self.decide(registration=reg)['accepted'])
        entry=self.evidence(); entry['reference']['normalized_bbox']=[0,0,.1,.1]
        self.assertFalse(self.decide(entry=entry)['accepted'])
        self.assertFalse(self.decide(similarities=[.85])['accepted'])
        self.assertFalse(self.decide(similarities=[.60])['accepted'])
        self.assertFalse(self.decide(targeted=dict(completed=False,objects=[]))['accepted'])
        self.assertFalse(self.decide(targeted=dict(completed=True,objects=[dict(label='mouse')]))['accepted'])
        self.assertFalse(self.decide(cloud=dict(status='unavailable'))['accepted'])
        for field in ['same_object_found','plausibly_moved_elsewhere','region_visible','region_unoccluded','absent_from_monitored_region','confidence']:
            cloud=self.cloud()
            cloud['result'][field]=.7 if field=='confidence' else not cloud['result'][field]
            self.assertFalse(self.decide(cloud=cloud)['accepted'],field)

    def test_accepted_removal_is_persisted_once_and_original_scan_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'test.db')
            for scan_id,previous,objects in [('b',None,[dict(id='mouse-detection',label='mouse',confidence=.88,
                           normalized_bbox=[.4,.4,.5,.5],center=[.45,.45])]),('a','b',[])]:
                store.create_scan(scan_id,'storage-a','2026-10-11T20:00:00Z','fixture.jpg')
                store.finish(scan_id,dict(objects=objects),dict(events=[],counts=dict(added=0,removed=0,moved=0,unchanged=0,uncertain=0)),previous,{'mouse-detection':'mouse-stable'})
            original=store.scan('a')['result_json']
            store.queue_removal_review('a')
            rejected=self.decide(similarities=[.8])
            store.save_removal_review('a',[rejected])
            with store.connection() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM change_events WHERE type="REMOVED"').fetchone()[0],0)
            accepted=self.decide()
            store.save_removal_review('a',[accepted])
            store.save_removal_review('a',[accepted])
            with store.connection() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM change_events WHERE type="REMOVED"').fetchone()[0],1)
            self.assertEqual(store.scan('a')['result_json'],original)
            self.assertEqual(store.public_scan(store.scan('a'))['result']['counts']['removed'],1)
            self.assertEqual(store.memory('storage-a')[0]['status'],'REMOVED')
            self.assertEqual(Store(store.path).memory('storage-a')[0]['status'],'REMOVED')

    def test_only_explicitly_selected_candidates_are_enrolled(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'test.db')
            store.create_scan('b','storage-a','2026-10-11T20:00:00Z','fixture.jpg')
            objects=[dict(id=k,label=k,confidence=.5,normalized_bbox=[.4,.4,.5,.5],center=[.45,.45]) for k in ['mouse','noise']]
            store.finish('b',dict(objects=objects),dict(events=[],counts={}),None,{'mouse':'mouse','noise':'noise'})
            registry=dict(reference_image='fixture.jpg',status='AWAITING_USER_CONFIRMATION',objects=[dict(object_id=k,reference=dict(id=k,normalized_bbox=[.4,.4,.5,.5]),display_name=k,confirmed=False,state='ENROLLMENT_CANDIDATE') for k in ['mouse','noise']])
            with patch.object(store,'load_registry',return_value=registry):
                store.confirm_baseline('storage-a','b',[dict(object_id='mouse',display_name='Mouse')])
                with self.assertRaises(ValueError):
                    store.confirm_baseline('loading-area','b',[dict(object_id='mouse',display_name='Mouse')])
                with self.assertRaises(ValueError):
                    store.confirm_baseline('storage-a','b',[dict(object_id='unknown',display_name='Mouse')])
            with store.connection() as db:
                self.assertEqual([r['object_id'] for r in db.execute('SELECT * FROM registry_enrollments')],['mouse'])


if __name__=='__main__':
    unittest.main()
