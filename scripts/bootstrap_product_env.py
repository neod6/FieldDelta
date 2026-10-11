"""Copy an already available process credential into ignored local config, never stdout."""
import os
from pathlib import Path

root=Path(__file__).resolve().parents[1]
target=root/'.env'
if not target.exists():
    key=os.environ.get('OPENAI_API_KEY','')
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as handle:
        handle.write('OPENAI_API_KEY='+key+'\nOPENAI_MODEL=gpt-4.1\nCLOUD_VISION_ENABLED=true\nFIELDDELTA_DB=data/fielddelta.db\n')
    print('Ignored project .env initialized; credential value not displayed.')
else:
    print('Existing project .env preserved.')
