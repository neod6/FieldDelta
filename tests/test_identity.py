import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.store import Store
from backend.app import create_app
from test_product import StubService


class IdentityTests(unittest.TestCase):
    def test_operator_links_share_rename_without_upgrading_vision_or_rewriting_raw(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.object(Store,'registry_path',return_value=root/'registry.json'):
                store=Store(root/'test.db')
                obj=dict(id='bag-before',label='fabric clothing',confidence=.4,normalized_bbox=[.1,.1,.4,.4],center=[.25,.25])
                (root/'registry.json').write_text(json.dumps(dict(reference_image='before.jpg',status='AWAITING_USER_CONFIRMATION',objects=[dict(object_id='baseline-bag',reference=obj,display_name=obj['label'],confirmed=False,state='CANDIDATE')])))
                store.create_scan('before','loading-area','2026-10-11T22:00:00Z','before.jpg')
                store.finish('before',dict(objects=[obj]),dict(events=[]),None,{'bag-before':'baseline-bag'})
                store.create_scan('after','loading-area','2026-10-11T22:01:00Z','after.jpg')
                after={**obj,'id':'bag-after','label':'bag'}
                store.finish('after',dict(objects=[after]),dict(events=[],counts=dict(uncertain=1)),'before',{'bag-after':'after-bag'})
                original=store.scan('after')['result_json']
                store.correct_identity('loading-area','baseline-bag','Fabric Clothing')
                store.link_identity('loading-area','baseline-bag','after-bag')
                store.correct_identity('loading-area','after-bag','Backpack')
                with self.assertRaises(ValueError):
                    store.link_identity('storage-a','baseline-bag','after-bag')
                with self.assertRaises(ValueError):
                    store.link_identity('loading-area','after-bag','baseline-bag')
                restarted=Store(root/'test.db')
                for scan_id in ('before','after'):
                    self.assertEqual(restarted.product_objects(restarted.scan(scan_id))[0]['label'],'Backpack')
                self.assertEqual(restarted.objects('after')[0]['label'],'bag')
                self.assertEqual(restarted.scan('after')['result_json'],original)
                self.assertEqual(restarted.registry('loading-area')['objects'][0]['confirmed'],False)

    def test_food_and_dish_names_are_persistent_identity_not_class_filters(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.object(Store,'registry_path',return_value=root/'registry.json'):
                store=Store(root/'test.db')
                objects=[dict(id='food',label='package',confidence=.45,normalized_bbox=[.2,.4,.4,.6],center=[.3,.5]),
                         dict(id='dish',label='earbud case',confidence=.35,normalized_bbox=[.1,.3,.6,.8],center=[.35,.55])]
                (root/'registry.json').write_text(json.dumps(dict(reference_image='before.jpg',objects=[
                    dict(object_id=o['id'],reference=o,display_name=o['label'],confirmed=False,state='CANDIDATE') for o in objects])))
                store.create_scan('before','loading-area','2026-10-11T22:00:00Z','before.jpg')
                store.finish('before',dict(objects=objects),dict(events=[]),None,{'food':'food','dish':'dish'})
                store.confirm_baseline('loading-area','before',[dict(object_id='food',display_name='Sandwich'),dict(object_id='dish',display_name='Plate')])
                store.create_scan('after','loading-area','2026-10-11T22:01:00Z','after.jpg')
                after=[{**o,'id':o['id']+'-after','label':'food' if o['id']=='food' else 'dish'} for o in objects]
                store.finish('after',dict(objects=after),dict(events=[dict(object_id=o['id'],label='different class',type='UNCHANGED') for o in objects]),'before',{'food-after':'food','dish-after':'dish'})
                restarted=Store(root/'test.db')
                self.assertEqual({o['label'] for o in restarted.product_objects(restarted.scan('after'))},{'Sandwich','Plate'})
                self.assertEqual({o['label'] for o in restarted.objects('after')},{'food','dish'})
                self.assertEqual(restarted.identity('loading-area','food')['raw_ai_label'],'package')

    def test_six_object_memory_rename_ignore_future_scan_and_restart(self):
        # Synthetic transport fixture; not a claim about physical scene recognition.
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.object(Store,'registry_path',return_value=root/'registry.json'):
                store=Store(root/'test.db')
                labels=['laptop computer','book','fabric clothing','bottle','can drink','mouse','noise']
                names=['Laptop','Notebook','Backpack','Water Bottle','Sprite Can','Mouse']
                objects=[dict(id=f'd{i}',label=l,confidence=.42,normalized_bbox=[.1,.1,.2,.2],center=[.15,.15]) for i,l in enumerate(labels)]
                registry=dict(reference_image='baseline.jpg',roi=[],status='AWAITING_USER_CONFIRMATION',objects=[dict(object_id=f's{i}',display_name=l,confirmed=False,state='CANDIDATE',reference=objects[i]) for i,l in enumerate(labels)])
                (root/'registry.json').write_text(json.dumps(registry))
                store.create_scan('baseline','loading-area','2026-10-11T22:00:00Z','baseline.jpg')
                store.finish('baseline',dict(objects=objects),dict(events=[],counts=dict(uncertain=7)),None,{o['id']:f's{i}' for i,o in enumerate(objects)})
                original=store.scan('baseline')['descriptor_json']
                with TestClient(create_app(root/'test.db',StubService)) as client:
                    response=client.post('/sites/loading-area/objects/s2/identity',json=dict(user_confirmed_name='Backpack'))
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual(response.json()['raw_ai_label'],'fabric clothing')
                    self.assertEqual(client.post('/sites/loading-area/objects/s6/identity',json=dict(ignored=True)).status_code,200)
                    selected=[dict(object_id=f's{i}',display_name=n) for i,n in enumerate(names)]
                    self.assertEqual(client.post('/sites/loading-area/confirm-baseline',json=dict(baseline_scan_id='baseline',objects=selected)).status_code,200)
                    self.assertEqual(client.post('/sites/loading-area/objects/s2/identity',json=dict(ignored=True)).status_code,409)
                    self.assertEqual(client.post('/sites/storage-a/objects/s2/identity',json=dict(user_confirmed_name='Wrong site')).status_code,409)
                store.create_scan('rescan','loading-area','2026-10-11T22:01:00Z','after.jpg')
                after=[{**o,'id':f'after{i}','label':'clothing' if i==2 else o['label']} for i,o in enumerate(objects)]
                events=[dict(object_id=f's{i}',label=o['label'],type='UNCHANGED') for i,o in enumerate(after[:6])]
                store.finish('rescan',dict(objects=after),dict(events=events,counts=dict(unchanged=6,uncertain=1)),'baseline',{o['id']:f's{i}' for i,o in enumerate(after)})
                restarted=Store(root/'test.db')
                self.assertEqual(restarted.scan('baseline')['descriptor_json'],original)
                self.assertEqual(len(restarted.scans('loading-area')),2)
                product=restarted.product_objects(restarted.scan('rescan'))
                self.assertEqual(len(product),6)
                self.assertEqual(next(o for o in product if o['stable_id']=='s2')['label'],'Backpack')
                self.assertEqual(next(o for o in restarted.objects('rescan') if o['stable_id']=='s2')['label'],'clothing')
                self.assertEqual(len(restarted.objects('rescan')),7)
                self.assertEqual(next(o for o in restarted.memory('loading-area') if o['stable_id']=='s2')['label'],'Backpack')
                self.assertEqual(next(o for o in restarted.public_scan(restarted.scan('rescan'))['object_results'] if o['object_id']=='s2')['label'],'Backpack')
                self.assertEqual(restarted.identity('loading-area','s2')['confirmed_by'],'demo_operator')
                self.assertEqual(len([o for o in restarted.memory('loading-area') if o['enrollment_status']=='CONFIRMED']),6)
                with TestClient(create_app(root/'test.db',StubService)) as client:
                    detail=client.get('/scans/rescan/detail').json()
                    self.assertEqual(next(o for o in detail['product_objects'] if o['stable_id']=='s2')['label'],'Backpack')
                    self.assertEqual(next(o for o in detail['detected_objects'] if o['stable_id']=='s2')['label'],'clothing')
                    phone=client.get('/scans/rescan').json()
                    self.assertEqual(next(o for o in phone['object_results'] if o['object_id']=='s2')['label'],'Backpack')
                    self.assertTrue(all('reason' in o for o in phone['object_results']))
                    self.assertEqual(len(phone['object_results']),6)
                store.create_scan('missing','loading-area','2026-10-11T22:02:00Z','missing.jpg')
                store.finish('missing',dict(objects=[]),dict(events=[],counts=dict(uncertain=6)),'rescan',{})
                review=next(o for o in store.public_scan(store.scan('missing'))['object_results'] if o['object_id']=='s2')
                self.assertEqual(review['label'],'Backpack')
                self.assertEqual(review['status'],'UNCERTAIN')
                with store.connection() as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM change_events WHERE type="REMOVED"').fetchone()[0],0)


if __name__=='__main__':
    unittest.main()
