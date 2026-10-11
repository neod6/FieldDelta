"""Evaluate the unchanged Phase 0 pipeline on all pairs of supplied photos."""
import itertools
import json
from pathlib import Path
import sys
import statistics

from PIL import Image, ImageOps, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.vision import VisionPipeline
from backend.matching import compare, public_object


def main():
    paths = sorted((ROOT / 'test_images' / 'user_batch').glob('*.jpg'))
    output = ROOT / 'results' / 'user_batch'
    output.mkdir(parents=True, exist_ok=True)
    sheet = Image.new('RGB', (1200, 4 * 440), 'white')
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        with Image.open(path) as source:
            preview = ImageOps.exif_transpose(source).convert('RGB')
        preview.thumbnail((590, 400))
        x, y = (index % 2)*600, (index // 2)*440
        sheet.paste(preview, (x, y+30))
        draw.text((x+10, y+5), path.stem, fill='black')
    sheet.save(output / 'overview.jpg')
    pipeline = VisionPipeline()
    scans = {p.stem: pipeline.extract(p, output / p.stem) for p in paths}
    pairs = []
    for old, new in itertools.combinations(scans, 2):
        delta = compare(scans[old]['objects'], scans[new]['objects'])
        pairs.append(dict(before=old, after=new, **delta))
    result = dict(scans=scans, pairs=pairs,
                  note='All 21 pairs evaluated with unchanged Phase 0 settings. Physical ground truth requires visual review and user confirmation.')
    (output / 'evaluation.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    summary = dict(scans={name:dict(objects=[public_object(o) for o in scan['objects']],
                                   latency_seconds=scan['latency_seconds']) for name, scan in scans.items()},
                   pairs=[{k:v for k,v in pair.items() if k != 'events'} for pair in pairs],
                   average_inference_seconds=statistics.mean(s['latency_seconds'] for s in scans.values()))
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
