"""Build an explicit static asset bundle for Vercel or Cloudflare Pages."""
import json
import os
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from play_anything.core.repository_graph import build_repository_graph

ASSETS = ('creator.html', 'creator.css', 'creator.js', 'creator-model.js',
          'creator-enhancements.js', 'creator-enhancements.css', 'hosting-model.js',
          'pitch-studio.js', 'cloud-plans.js', 'graph.html', 'graph.css',
          'graph-viewer.js', 'graph-page.js', 'dashboard.html')


def build(output=None):
    output = Path(output) if output else ROOT / 'site-dist'
    url, key = os.environ.get('SUPABASE_URL', ''), os.environ.get('SUPABASE_PUBLISHABLE_KEY', '')
    if bool(url) != bool(key):
        raise ValueError('Set both public Supabase variables or leave both unset.')
    if url:
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not re.fullmatch(r'[a-z0-9-]+\.supabase\.co', parsed.netloc) or parsed.path not in ('','/') or parsed.query or parsed.fragment:
            raise ValueError('SUPABASE_URL must be the HTTPS project URL.')
        if not re.fullmatch(r'sb_publishable_[A-Za-z0-9_-]+', key):
            raise ValueError('Only a Supabase publishable key may be included in the static bundle.')
    output.mkdir(parents=True, exist_ok=True)
    for name in ASSETS:
        shutil.copyfile(ROOT / 'play_anything' / name, output / name)
    shutil.copyfile(output / 'creator.html', output / 'index.html')
    (output / 'public-config.js').write_text('window.PlayCloudConfig = '+json.dumps(dict(mode="static",supabaseUrl=url,publishableKey=key))+';\n')
    (output / 'repository-graph.json').write_text(json.dumps(build_repository_graph(ROOT),separators=(',',':')))
    (output / '_headers').write_text('/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n  X-Frame-Options: SAMEORIGIN\n')
    print(f'Static site ready: {output}. No deployment performed.')
    return output


if __name__ == '__main__':
    build()
