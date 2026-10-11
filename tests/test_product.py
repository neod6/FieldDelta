import io
import tempfile
import time
import unittest
from unittest.mock import MagicMock,patch
from types import SimpleNamespace
import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from backend.app import create_app
from backend.cloud import Comparison
from backend.hybrid import fuse
from backend.cloud import compare_cloud


class StubService:
    """Transport fixture, not a vision accuracy test."""
    def __init__(self, store):
        self.store = store

    def process(self, scan_id):
        scan = self.store.scan(scan_id)
        previous = self.store.latest(scan['site_id'], exclude=scan_id)
        self.store.finish(scan_id, {'objects': [dict(id=scan_id+'-object', label='fixture', confidence=.5,
                          normalized_bbox=[.1,.1,.2,.2], center=[.15,.15])]},
                          {'counts': dict(added=0, removed=0, moved=0, unchanged=0, uncertain=0)},
                          previous['id'] if previous else None, {scan_id+'-object':'fixture-stable'})


class ProductTests(unittest.TestCase):
    def test_upload_validation_persistence_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.db'
            stream = io.BytesIO()
            Image.new('RGB', (16, 16)).save(stream, format='JPEG')
            data = dict(account_id='demo-warehouse', site_id='storage-a', timestamp='2026-10-11T12:00:00Z')
            files = {'image': ('photo.jpg', stream.getvalue(), 'image/jpeg')}
            with TestClient(create_app(path, StubService)) as client:
                self.assertEqual(len(client.get('/accounts').json()), 2)
                self.assertFalse(client.get('/sites/storage-a/state').json()['has_baseline'])
                self.assertEqual(client.post('/sites/storage-a/scan', data={**data, 'account_id': 'campus-lab'}, files=files).status_code, 403)
                self.assertEqual(client.post('/sites/storage-a/scan', data={**data, 'site_id': 'desk-01'}, files=files).status_code, 400)
                self.assertEqual(client.post('/sites/storage-a/scan', data={**data, 'timestamp': 'yesterday'}, files=files).status_code, 422)
                self.assertEqual(client.post('/sites/storage-a/scan', data=data, files={'image': ('bad.jpg', b'bad')}).status_code, 415)
                ids = []
                for _ in range(2):
                    response = client.post('/sites/storage-a/scan', data=data, files=files)
                    self.assertEqual(response.status_code, 202)
                    scan_id = response.json()['id']
                    ids.append(scan_id)
                    for _ in range(100):
                        scan = client.get('/scans/' + scan_id).json()
                        if scan['processing_status'] == 'complete':
                            break
                        time.sleep(.01)
                    self.assertEqual(scan['processing_status'], 'complete')
                    self.assertNotIn('image_path', scan)
                self.assertEqual(scan['previous_scan_id'], ids[0])
                self.assertEqual(len(client.get('/sites/storage-a/state').json()['objects']), 1)
                self.assertEqual(client.get('/scans/' + ids[0] + '/image').status_code, 200)
            with TestClient(create_app(path, StubService)) as client:
                self.assertTrue(client.get('/sites/storage-a/state').json()['has_baseline'])
                self.assertEqual(len(client.get('/sites/storage-a/scans').json()), 2)

    def comparison(self):
        return dict(matches=[dict(object_id='can', label='silver can', before_box=[.1,.1,.2,.2],
                                 after_box=[.1,.1,.2,.2], confidence=.9, evidence='Same appearance')],
                    added=[], removed=[], moved=[], unchanged=['can'], uncertain=[],
                    camera_motion=dict(changed=True, confidence=.8, description='Viewpoint changed'))

    def test_schema_rejects_conflicting_identity(self):
        data = self.comparison()
        Comparison.model_validate(data)
        data['moved'] = ['can']
        with self.assertRaises(ValidationError):
            Comparison.model_validate(data)

    def test_hybrid_agreement_and_disagreement(self):
        cloud = self.comparison()
        before = dict(objects=[dict(id='b', normalized_bbox=[.1,.1,.2,.2])])
        after = dict(objects=[dict(id='a', normalized_bbox=[.1,.1,.2,.2])])
        event = dict(before_id='b', after_id='a', object_id='stable-can', type='UNCHANGED',
                     evidence=dict(visual_similarity=.9), alternative_cost_margin=.1)
        result = fuse(dict(events=[event]), cloud, before, after, dict(reliable=True))
        self.assertEqual(result['counts']['unchanged'], 1)
        event['type'] = 'MOVED'
        self.assertEqual(fuse(dict(events=[event]), cloud, before, after, dict(reliable=True))['counts']['uncertain'], 1)
        event['type'] = 'UNCHANGED'
        self.assertEqual(fuse(dict(events=[event]), cloud, before, after, dict(reliable=False))['counts']['uncertain'], 1)

    def test_one_sided_observation_is_not_counted_twice(self):
        cloud = self.comparison()
        cloud['matches'][0]['after_box'] = None
        cloud['unchanged'] = []
        cloud['uncertain'] = [dict(object_id='can', reason='Not clearly observed')]
        event = dict(before_id='b', after_id=None, object_id='stable-can', type='NOT_OBSERVED')
        result = fuse(dict(events=[event]), cloud,
                      dict(objects=[dict(id='b', normalized_bbox=[.1,.1,.2,.2])]),
                      dict(objects=[]), dict(reliable=True))
        self.assertEqual(result['counts']['uncertain'], 1)
        self.assertEqual(result['events'][0]['object_id'], 'stable-can')

    def test_luminal_joint_images_and_bounded_503_retry(self):
        response=SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(self.comparison())))],
                                 model='test-model',usage=None,id='test-response')
        raw=SimpleNamespace(status_code=200,parse=lambda:response)
        unavailable=RuntimeError('test service unavailable')
        unavailable.status_code=503
        api=MagicMock()
        api.chat.completions.with_raw_response.create.side_effect=[unavailable,unavailable,raw]
        context=MagicMock()
        context.__enter__.return_value=api
        with patch('backend.cloud.settings',return_value=dict(key='unit-test-not-real',enabled=True,model='test-model')), \
             patch('backend.cloud.client',return_value=context), \
             patch('backend.cloud.image_url',return_value='data:image/jpeg;base64,test'), \
             patch('backend.cloud.time.sleep') as sleep, \
             patch('backend.cloud.random.uniform',return_value=0):
            result=compare_cloud('before.jpg','after.jpg')
        self.assertEqual(result['http_status'],200)
        self.assertEqual(len(result['transport_attempts']),3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list],[2,5])
        request=api.chat.completions.with_raw_response.create.call_args.kwargs
        self.assertEqual(sum(c['type']=='image_url' for c in request['messages'][0]['content']),2)
        self.assertEqual(request['response_format'],dict(type='json_object'))


if __name__ == '__main__':
    unittest.main()
