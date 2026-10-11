"""Exercise actual development photos against the running Mac backend."""
import json
from pathlib import Path
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    records = []
    with httpx.Client(base_url='http://127.0.0.1:8000', timeout=60) as client:
        client.get('/health').raise_for_status()
        for name in ['IMG_3377', 'IMG_3378']:
            started = time.perf_counter()
            with (ROOT / 'test_images' / 'user_batch' / (name + '.jpg')).open('rb') as image:
                response = client.post('/sites/equipment-room/scan',
                    data=dict(account_id='campus-lab', site_id='equipment-room', timestamp='2026-10-11T20:00:00Z'),
                    files=dict(image=(name + '.jpg', image, 'image/jpeg')))
            response.raise_for_status()
            scan_id = response.json()['id']
            for _ in range(300):
                response = client.get('/scans/' + scan_id)
                response.raise_for_status()
                record = response.json()
                if record['processing_status'] in ('complete', 'failed'):
                    break
                time.sleep(1)
            record.update(development_photo=name, total_seconds=round(time.perf_counter()-started, 2))
            records.append(record)
            print(name, record['processing_status'], (record.get('result') or {}).get('counts'), flush=True)
            if record['processing_status'] != 'complete':
                break
    path = ROOT / 'results' / 'product_live_test.json'
    path.write_text(json.dumps(dict(data_split='DEVELOPMENT_ONLY', records=records), indent=2))


if __name__ == '__main__':
    main()
