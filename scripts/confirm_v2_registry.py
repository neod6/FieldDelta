"""User/operator confirmation of actual enrollment candidates, not automatic labels."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.v2.tracking import confirm_registry

parser=argparse.ArgumentParser()
parser.add_argument('--registry',type=Path,required=True)
parser.add_argument('--names',type=Path,required=True,help='JSON mapping candidate IDs to operator-chosen names')
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
registry=json.loads(args.registry.read_text())
names=json.loads(args.names.read_text())
confirm_registry(registry,names)
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(registry,indent=2,allow_nan=False))
print(f'Confirmed {len(names)} identities; registry saved to {args.output}')
