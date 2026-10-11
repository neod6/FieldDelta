"""Real pretrained local detector and crop descriptors."""

from pathlib import Path
import os
import time

import certifi
import cv2
import numpy as np
from PIL import Image, ImageOps
import torch
from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('SSL_CERT_FILE', certifi.where())
os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / 'data' / 'ultralytics'))
from ultralytics import YOLO


class VisionPipeline:
    def __init__(self, device='cpu', confidence=0.30):
        if device not in ('cpu', 'mps'):
            raise ValueError('Supported devices: cpu, mps')
        if not 0 < confidence < 1:
            raise ValueError('Confidence must be between 0 and 1')
        self.device, self.confidence = device, confidence
        model_dir = ROOT / 'data' / 'models'
        model_dir.mkdir(parents=True, exist_ok=True)
        torch.hub.set_dir(str(model_dir / 'torch'))
        self.detector = YOLO(str(model_dir / 'yolo11n.pt'))
        weights = MobileNet_V3_Small_Weights.DEFAULT
        self.encoder = mobilenet_v3_small(weights=weights).to(device).eval()
        self.transforms = weights.transforms()

    def extract(self, path, artifact_dir=None):
        started = time.perf_counter()
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert('RGB')
        image.thumbnail((2048, 2048))
        width, height = image.size
        prediction = self.detector.predict(image, conf=self.confidence, imgsz=640,
                                           device=self.device, verbose=False)[0]
        objects, crops = [], []
        if artifact_dir is not None:
            artifact_dir = Path(artifact_dir)
            artifact_dir.mkdir(parents=True, exist_ok=True)
            Image.fromarray(prediction.plot()[:, :, ::-1]).save(artifact_dir / 'detections.jpg')
        for index, box in enumerate(prediction.boxes):
            x1, y1, x2, y2 = box.xyxy[0].cpu().tolist()
            bounds = [max(0, int(x1)), max(0, int(y1)), min(width, int(x2)), min(height, int(y2))]
            if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
                continue
            crop = image.crop(bounds)
            hsv = cv2.cvtColor(np.asarray(crop), cv2.COLOR_RGB2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256]).flatten()
            hist = hist / max(float(hist.sum()), 1)
            obj = dict(id=f'object_{index:03d}', label=prediction.names[int(box.cls.item())],
                       confidence=float(box.conf.item()), bbox=bounds,
                       normalized_bbox=[bounds[0]/width, bounds[1]/height, bounds[2]/width, bounds[3]/height],
                       center=[(x1+x2)/(2*width), (y1+y2)/(2*height)],
                       area=(x2-x1)*(y2-y1)/(width*height), color=hist.tolist())
            if artifact_dir is not None:
                crop_path = artifact_dir / f'{obj["id"]}.jpg'
                crop.save(crop_path)
                obj['crop_path'] = str(crop_path)
            objects.append(obj)
            crops.append(self.transforms(crop))
        with torch.inference_mode():
            for start in range(0, len(crops), 16):
                batch = torch.stack(crops[start:start+16]).to(self.device)
                encoded = self.encoder.avgpool(self.encoder.features(batch)).flatten(1)
                encoded = torch.nn.functional.normalize(encoded, dim=1).cpu().numpy()
                for obj, vector in zip(objects[start:start+16], encoded):
                    obj['embedding'] = vector.tolist()
        return dict(image_path=str(Path(path).resolve()), width=width, height=height,
                    objects=objects, latency_seconds=time.perf_counter()-started)
