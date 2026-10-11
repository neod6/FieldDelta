import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.matching import compare, public_object, MatchSettings
from backend.vision import VisionPipeline


def main():
    parser = argparse.ArgumentParser(description='Compare two real photos with pretrained models')
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'results' / 'scene_comparison')
    parser.add_argument('--device', choices=['cpu', 'mps'], default='cpu')
    args = parser.parse_args()
    for path in (args.before, args.after):
        if not path.is_file():
            parser.error(f'Photo does not exist: {path}')
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    try:
        pipeline = VisionPipeline(args.device)
        before = pipeline.extract(args.before, args.output / 'before')
        after = pipeline.extract(args.after, args.output / 'after')
        result = compare(before['objects'], after['objects'])
        result.update(dict(before={**before, 'objects': [public_object(o) for o in before['objects']]},
                           after={**after, 'objects': [public_object(o) for o in after['objects']]},
                           models=['yolo11n', 'mobilenet_v3_small'], settings=asdict(MatchSettings()),
                           elapsed_seconds=time.perf_counter()-started,
                           warnings=['Fixed camera viewpoint required; movement is 2D, not world-space.',
                                     'Unmatched detections may reflect occlusion or missed detection, not physical changes.',
                                     'Matching scores are heuristic, not calibrated probabilities.',
                                     'Identical same-class objects may be ambiguous; review flagged events.']))
        with (args.output / 'result.json').open('w') as handle:
            json.dump(result, handle, indent=2, allow_nan=False)
        # Internal descriptors are saved separately for future snapshot persistence.
        with (args.output / 'descriptors.json').open('w') as handle:
            json.dump({'before': before, 'after': after}, handle, allow_nan=False)
        print(json.dumps(dict(counts=result['counts'], requires_review=result['requires_review'],
                             elapsed_seconds=result['elapsed_seconds'], output=str(args.output.resolve())), indent=2))
        if not before['objects'] or not after['objects']:
            print('WARNING: An image has no detections. This is not a validated physical-change result.')
    except Exception as error:
        print(f'Comparison failed ({type(error).__name__}): {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
