import io
import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from PIL import Image
from backend.images import normalize_upload
from backend.app import create_app
from test_product import StubService


class OrientationTests(unittest.TestCase):
    def test_all_exif_orientations_are_baked_and_idempotent(self):
        source=Image.new('RGB',(3,2))
        source.putdata([(255,0,0),(0,255,0),(0,0,255),(255,255,0),(0,255,255),(255,0,255)])
        transforms={1:None,2:Image.Transpose.FLIP_LEFT_RIGHT,3:Image.Transpose.ROTATE_180,
                    4:Image.Transpose.FLIP_TOP_BOTTOM,5:Image.Transpose.TRANSPOSE,
                    6:Image.Transpose.ROTATE_270,7:Image.Transpose.TRANSVERSE,8:Image.Transpose.ROTATE_90}
        for value,method in transforms.items():
            with self.subTest(orientation=value):
                image=source.copy(); image.getexif()[274]=value
                normalized,info=normalize_upload(image)
                expected=source.transpose(method) if method is not None else source
                self.assertEqual(normalized.tobytes(),expected.tobytes())
                self.assertEqual(normalized.size,expected.size)
                self.assertNotIn(274,normalized.getexif())
                self.assertEqual(normalize_upload(normalized)[0].tobytes(),normalized.tobytes())

    def test_missing_exif_uses_capture_orientation_without_double_rotation(self):
        source=Image.new('RGB',(30,20))
        image,info=normalize_upload(source,8)
        self.assertEqual(image.size,(20,30))
        source.getexif()[274]=6
        image,info=normalize_upload(source,8)
        self.assertEqual(info['applied_orientation'],6)
        self.assertEqual(image.size,(20,30))

    def test_upload_normalizes_before_processing_and_keeps_source(self):
        with tempfile.TemporaryDirectory() as directory:
            with TestClient(create_app(Path(directory)/'test.db',StubService)) as client:
                raw=io.BytesIO(); Image.new('RGB',(30,20)).save(raw,format='JPEG')
                fields=dict(account_id='demo-warehouse',site_id='storage-a',timestamp='2026-10-11T22:00:00Z',image_orientation='8')
                response=client.post('/sites/storage-a/scan',data=fields,files={'image':('landscape.jpg',raw.getvalue(),'image/jpeg')})
                self.assertEqual(response.status_code,202,response.text)
                path=Path(client.app.state.store.scan(response.json()['id'])['image_path'])
                with Image.open(path) as canonical:
                    self.assertEqual(canonical.size,(20,30))
                    self.assertNotIn(274,canonical.getexif())
                self.assertEqual(path.with_suffix('.original').read_bytes(),raw.getvalue())
                self.assertEqual(json.loads(path.with_suffix('.upload.json').read_text())['applied_orientation'],8)
                self.assertEqual(client.post('/sites/storage-a/scan',data={**fields,'image_orientation':'9'},files={'image':('x.jpg',raw.getvalue(),'image/jpeg')}).status_code,422)


if __name__=='__main__':
    unittest.main()
