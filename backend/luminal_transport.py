"""Mac-only Luminal configuration and one-shot image-input probe."""
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]


def settings():
    load_dotenv(ROOT / '.env', override=True)
    # Reuse the existing ignored Mac credentials; never copy them to the client.
    if not os.getenv('LUMINAL_API_KEY'):
        load_dotenv(ROOT.parent / 'autoevolve' / '.env', override=False)
    return dict(key=os.getenv('LUMINAL_API_KEY', ''),
                base_url=os.getenv('LUMINAL_BASE_URL', 'https://flash.luminal.cloud/v1'),
                model=os.getenv('LUMINAL_MODEL', 'deepseek-ai/DeepSeek-V4.1-Flash'),
                enabled=os.getenv('CLOUD_VISION_ENABLED', 'true').lower() == 'true')


def client(config, retries=0):
    if not config['key']:
        raise RuntimeError('LUMINAL_API_KEY is missing from Mac configuration')
    return OpenAI(api_key=config['key'], base_url=config['base_url'], timeout=120, max_retries=retries)
