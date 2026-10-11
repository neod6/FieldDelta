"""Download official weights and exercise real inference on a public smoke photo."""
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.vision import VisionPipeline
from backend.matching import compare, public_object


def main():
    destination = ROOT / 'results' / 'model_smoke'
    destination.mkdir(parents=True, exist_ok=True)
    photo = destination / 'public_bus.jpg'
    if not photo.exists():
        urllib.request.urlretrieve('https://raw.githubusercontent.com/ultralytics/assets/main/im/bus.jpg', photo)
    pipeline = VisionPipeline()
    first = pipeline.extract(photo, destination / 'detections')
    second = pipeline.extract(photo)
    delta = compare(first['objects'], second['objects'])
    assert first['objects'], 'Real detector produced no objects on the smoke photo'
    assert delta['counts']['UNCHANGED'] == len(first['objects']), 'Identical-photo consistency failed'
    assert sum(delta['counts'][kind] for kind in ('ADDED', 'REMOVED', 'MOVED')) == 0
    result = dict(status='MODEL_SMOKE_PASS_NOT_PHASE_0_VALIDATION',
                  source='https://raw.githubusercontent.com/ultralytics/assets/main/im/bus.jpg',
                  detected_objects=[public_object(o) for o in first['objects']],
                  identical_photo_counts=delta['counts'],
                  inference_seconds=first['latency_seconds'],
                  note='Same public photo twice checks runtime consistency only. Real changed-scene user photos are still required.')
    (destination / 'smoke.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
