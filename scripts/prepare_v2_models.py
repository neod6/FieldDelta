from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.v2.models import OpenDetector, InstanceEncoder

if __name__=='__main__':
    OpenDetector()
    print('Grounding DINO tiny weights ready',flush=True)
    InstanceEncoder()
    print('DINOv2 small weights ready',flush=True)
