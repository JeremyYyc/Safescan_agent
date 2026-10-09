"""Resume the frozen regional batch in a new directory; never overwrite raw inputs."""
import argparse
from pathlib import Path
import shutil
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from collect import ROOT, digest, write_json
from flagstaff_collect import media_candidates
from source_fit_probe import run
from unilodge_regional_media import SOURCE, DETAILS, read, export

BASE = ROOT / 'data/collection-pilot/unilodge-regional-dataset-20260929'
REVIEWS = Path(__file__).with_name('unilodge_regional_reviews.json')
ADDITIONS = [
    ('Balcony', '1-bedroom-balcony-unilodge', None),
    ('2 Bedroom Deluxe Share with Balcony', '2-bedroom-deluxe-balcony-unilodge', None),
    ('2 Bedroom Deluxe Share', '2-bedroom-deluxe-ensuite-unilodge', None),
    ('2 Bedroom Penthouse Loft Share', 'penthouse-loft-standard-unilodge', 'Two Bedroom Penthouse Loft'),
    ('2 Bedroom Penthouse Loft Deluxe Share', 'penthouse-loft-deluxe-unilodge', None),
]


def prepare():
    selections = read(BASE / 'selections.json')
    rooms = read(DETAILS / 'room_types.json')
    plans = read(DETAILS / 'floorplan_candidates.json')
    meta = next(p for p in read(SOURCE / 'outcomes.json') if p['id'] == 'metro-adelaide')
    gallery = media_candidates((SOURCE / meta['local_path']).read_bytes(), meta)
    for name, token, label in ADDITIONS:
        room = next(r for r in rooms if r['property_id'] == 'metro-adelaide' and r['name'] == name)
        matches = [p for p in plans if p['property_id'] == 'metro-adelaide' and token in p['url']]
        if len(matches) != 1:
            raise ValueError('ambiguous_plan:' + name)
        photos = ([p for p in gallery if p['label'].strip() == label and '_wide.' in p['url']][:3]
                  if label else room['photos'][:2])
        selections.append({'room_id': room['id'], 'property_id': room['property_id'], 'name': name,
                           'city': room['city'], 'association_status': 'source_labels_pending_visual_review',
                           'assets': [{'url': matches[0]['url'], 'role': 'layout', 'source_label': matches[0]['label']}]
                           + [{'url': p['url'], 'role': 'interior_candidate', 'source_label': p.get('label')} for p in photos]})
    # Request an uncropped derivative of the same public CDN asset, retaining provenance.
    for s in selections:
        if s['property_id'] == 'melbourne-central' and s['name'] in ('Studio Queen', '2 Bedroom Apartment'):
            original = s['assets'][0]
            parts = urlsplit(original['url'])
            query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k != 'crop'])
            s['assets'].append({**original, 'url': urlunsplit(parts._replace(query=query)),
                                'derived_from_url': original['url'], 'transform': 'remove_CDN_crop_parameter'})
    old = {a['url'] for s in read(BASE / 'selections.json') for a in s['assets']}
    urls = sorted({a['url'] for s in selections for a in s['assets']} - old)
    if len(urls) > 20:
        raise ValueError('supplement_budget')
    return selections, [{'id': 'asset-' + digest(u.encode())[:16], 'url': u, 'kind': 'image'} for u in urls]


def collect(output):
    if output.exists():
        raise ValueError('output_exists_use_export_only')
    selections, targets = prepare()
    shutil.copytree(BASE, output)
    write_json(output / 'selections.json', selections)
    shutil.copyfile(REVIEWS, output / 'visual_reviews.json')
    write_json(output / 'resume_manifest.json', {
        'base': str(BASE.relative_to(ROOT)), 'base_manifest_sha256': digest((BASE / 'export_manifest.json').read_bytes()),
        'script_sha256': digest(Path(__file__).read_bytes()), 'planned': targets,
        'review_config_sha256': digest(REVIEWS.read_bytes()),
    })
    run(output / 'supplement-20260930', targets)
    export(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--export-only', action='store_true')
    args = parser.parse_args()
    if args.export_only:
        shutil.copyfile(REVIEWS, args.output / 'visual_reviews.json')
        export(args.output.resolve())
    else:
        collect(args.output.resolve())
