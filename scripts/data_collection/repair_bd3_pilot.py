"""Fetch the author's public BD3 sample images for local category review."""
import json
from pathlib import Path
from urllib.parse import quote
from datetime import datetime, timezone
from collect import Fetcher, digest, write_json
from verify_general_housing import run

ROOT = Path('data/collection-pilot/repair-bd3-20261005')
CATEGORIES = ['Algae', 'major crack', 'minor crack', 'peeling', 'spalling', 'stain']


def main():
    ROOT.mkdir(parents=True, exist_ok=False)
    client = Fetcher(hosts={'api.github.com'})
    try:
        url = 'https://api.github.com/repos/Praveenkottari/BD3-Dataset/git/trees/main?recursive=1'
        _, status, _, body = client.get(url)
        if status != 200:
            raise ValueError(f'github_http_{status}')
        (ROOT / 'tree.json').write_bytes(body)
        tree = json.loads(body)
    finally:
        client.close()
    targets = []
    for category in CATEGORIES:
        prefix = f'sample images/class_images/{category}/'
        files = sorted(x['path'] for x in tree['tree'] if x['path'].startswith(prefix) and x['path'].endswith('.jpg'))
        for path in files[:5]:
            targets.append({'id': Path(path).stem, 'category': category, 'kind': 'image',
                            'url': 'https://raw.githubusercontent.com/Praveenkottari/BD3-Dataset/' + tree['sha'] + '/' + quote(path),
                            'source_path': path, 'source_commit': tree['sha'],
                            'source_url': 'https://github.com/Praveenkottari/BD3-Dataset',
                            'role': 'defect_example_not_work_order', 'usage_approved': False})
    write_json(ROOT / 'targets.json', targets)
    for offset in range(0, len(targets), 20):
        folder = ROOT / 'media' / f'{offset:03d}'
        run(targets[offset:offset + 20], folder)
        outcomes = json.loads((folder / 'outcomes.json').read_text(encoding='utf-8'))
        if any('host_forbidden' in x.get('error', '') or 'host_rate_limited' in x.get('error', '') for x in outcomes):
            break
    rows = []
    for p in sorted((ROOT / 'media').glob('*/outcomes.json')):
        for row in json.loads(p.read_text(encoding='utf-8')):
            if row['status'] == 'success':
                row['local_path'] = (p.parent / row['local_path']).relative_to(ROOT).as_posix()
            rows.append(row)
    write_json(ROOT / 'dataset.json', rows)
    write_json(ROOT / 'summary.json', {'retrieved_at': datetime.now(timezone.utc).isoformat(),
        'source': 'BD3 author repository', 'rights_status': 'unknown_pending_permission',
        'counts': {c: sum(r['category'] == c and r['status'] == 'success' for r in rows) for c in CATEGORIES}})
    write_json(ROOT / 'manifest.json', {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in ROOT.rglob('*') if p.is_file() and p.name != 'manifest.json'})


if __name__ == '__main__':
    main()
