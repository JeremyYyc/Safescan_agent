"""Follow-up: six explicitly page-linked images; no URL size guessing or video ripping."""
import argparse
import json
from pathlib import Path

from collect import ROOT
from source_fit_probe import run


def targets():
    def read(relative):
        return json.loads((ROOT / relative).read_text(encoding='utf-8'))
    rooms = read('data/collection-pilot/flagstaff-20260929-v1/room_types.json')
    room = next(r for r in rooms if r['name'] == 'Studio Standard')
    main = read('data/collection-pilot/flagstaff-20260929-v1/media_candidates.json')
    plan = next(a for a in main if '13m' in a['label'] and 'Standard Studio' in a['label'])
    novus = read('data/collection-pilot/novus-20260929/sample.json')
    urls = [('unilodge-main-plan', plan['url']), ('unilodge-interior-extra-1', room['photos'][3]['url']),
            ('unilodge-interior-extra-2', room['photos'][4]['url'])]
    urls += [('novus-' + str(i), a['url']) for i, a in enumerate(novus['assets'][:3])]
    return [{'id': name, 'url': url, 'kind': 'image'} for name, url in urls]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve(), targets())
