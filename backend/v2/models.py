import os
from pathlib import Path
import time

import certifi
import cv2
import numpy as np
from PIL import ImageDraw
ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault('SSL_CERT_FILE',certifi.where())
os.environ.setdefault('REQUESTS_CA_BUNDLE',certifi.where())
os.environ.setdefault('HF_HUB_DISABLE_XET','1')
import torch
from transformers import AutoImageProcessor, AutoModel, GroundingDinoProcessor, AutoModelForZeroShotObjectDetection

CACHE = str(ROOT / 'data' / 'models' / 'huggingface')
PROMPTS = ['laptop','computer','can','drink can','bottle','cup','mouse',
           'earbud case','headphone case','book','bag','fabric','clothing','phone','box','package',
           'sandwich','plate']


def box_iou(a,b):
    x1,y1,x2,y2 = max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3])
    intersection = max(x2-x1,0)*max(y2-y1,0)
    aa, ab = (a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1])
    return intersection / max(aa+ab-intersection,1e-8)


class OpenDetector:
    def __init__(self, local_only=False):
        self.processor = GroundingDinoProcessor.from_pretrained('IDEA-Research/grounding-dino-tiny',
                            cache_dir=CACHE, local_files_only=local_only)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(
            'IDEA-Research/grounding-dino-tiny', cache_dir=CACHE,
            local_files_only=local_only, use_safetensors=True).eval()

    def detect(self, image, output=None, prompts=None):
        started = time.perf_counter()
        # Ordinary scans retain fixed prompts; a separate absence search may target one object.
        selected_prompts=PROMPTS if prompts is None else prompts
        inputs = self.processor(images=image, text='. '.join(selected_prompts)+'.', return_tensors='pt')
        with torch.inference_mode():
            prediction = self.model(**inputs)
        result = self.processor.post_process_grounded_object_detection(prediction,
                    inputs.input_ids, threshold=.25, text_threshold=.25,
                    target_sizes=[(image.height,image.width)])[0]
        objects = []
        for score,label,box in zip(result['scores'],result['text_labels'],result['boxes']):
            bounds = box.cpu().tolist()
            bounds = [max(0,bounds[0]),max(0,bounds[1]),min(image.width,bounds[2]),min(image.height,bounds[3])]
            if bounds[2]-bounds[0] < 8 or bounds[3]-bounds[1] < 8:
                continue
            objects.append(dict(label=label, semantic_suggestions=[label], confidence=float(score),bbox=bounds))
        # Merge duplicate proposals for the same region, retaining semantic suggestions.
        kept = []
        for obj in sorted(objects,key=lambda o:o['confidence'],reverse=True):
            duplicate = next((k for k in kept if box_iou(obj['bbox'],k['bbox']) > .65),None)
            if duplicate:
                duplicate['semantic_suggestions'].append(obj['label'])
                continue
            obj['id'] = f'candidate_{len(kept):03d}'
            x1,y1,x2,y2=obj['bbox']
            obj.update(normalized_bbox=[x1/image.width,y1/image.height,x2/image.width,y2/image.height],
                       center=[(x1+x2)/2/image.width,(y1+y2)/2/image.height],
                       area=(x2-x1)*(y2-y1)/image.width/image.height)
            kept.append(obj)
        if output:
            output=Path(output)
            output.mkdir(parents=True,exist_ok=True)
            annotated=image.copy()
            draw=ImageDraw.Draw(annotated)
            for obj in kept:
                draw.rectangle(obj['bbox'],outline='lime',width=3)
                draw.text(tuple(obj['bbox'][:2]),f'{obj["id"]} {obj["label"]} {obj["confidence"]:.2f}',fill='red')
            annotated.save(output/'detections.jpg')
        return dict(objects=kept, latency_seconds=time.perf_counter()-started,
                    model='IDEA-Research/grounding-dino-tiny', prompts=selected_prompts)


class InstanceEncoder:
    def __init__(self, local_only=False):
        self.processor=AutoImageProcessor.from_pretrained('facebook/dinov2-small', cache_dir=CACHE,
                        local_files_only=local_only, use_fast=True)
        self.model=AutoModel.from_pretrained('facebook/dinov2-small',cache_dir=CACHE,
                        local_files_only=local_only,use_safetensors=True).eval()

    def encode(self, image, objects, output=None):
        started=time.perf_counter()
        crops=[image.crop(tuple(o['bbox'])).convert('RGB') for o in objects]
        for start in range(0,len(crops),8):
            inputs=self.processor(images=crops[start:start+8], return_tensors='pt')
            with torch.inference_mode():
                features=self.model(**inputs).last_hidden_state[:,0]
                features=torch.nn.functional.normalize(features,dim=1).cpu().numpy()
            for obj,crop,feature in zip(objects[start:start+8],crops[start:start+8],features):
                obj['embedding']=feature.tolist()
                hsv=cv2.cvtColor(np.asarray(crop),cv2.COLOR_RGB2HSV)
                hist=cv2.calcHist([hsv],[0,1],None,[16,8],[0,180,0,256]).ravel()
                obj['color']=(hist/max(float(hist.sum()),1)).tolist()
                if output:
                    path=Path(output)/f'{obj["id"]}.jpg'
                    path.parent.mkdir(parents=True,exist_ok=True)
                    crop.save(path)
                    obj['crop_path']=str(path)
        return time.perf_counter()-started
