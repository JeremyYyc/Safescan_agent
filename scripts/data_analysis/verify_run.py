"""Verify hashes, JSON/SQLite consistency and deterministic offline replay."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3

from baseline import ROOT, read, sha


def verify(path):
    manifest = read(path / 'manifest.json')
    for item in manifest['inputs']:
        if sha(ROOT / item['path']) != item['sha256']:
            raise ValueError('input_changed: ' + item['path'])
    for name, digest in manifest['outputs'].items():
        if sha(path / name) != digest:
            raise ValueError('output_changed: ' + name)
    summary = read(path / 'summary.json')
    checks = read(path / 'checks.json')
    with closing(sqlite3.connect(f'{(path / "analysis.sqlite").resolve().as_uri()}?mode=ro', uri=True)) as db:
        for name in ('samples', 'offers', 'units', 'assets'):
            expected = len(read(path / (name + '.json')))
            if db.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0] != expected:
                raise ValueError('sql_count_mismatch: ' + name)
        if db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('foreign_key_check_failed')
        if db.execute('SELECT SUM(quality_pass) FROM checks').fetchone()[0] != sum(c['quality_pass'] for c in checks):
            raise ValueError('sql_metric_mismatch')
    if summary['counts']['samples'] != len(checks):
        raise ValueError('summary_denominator_mismatch')
    return len(manifest['outputs'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--compare', type=Path)
    args = parser.parse_args()
    print('Verified outputs:', verify(args.run))
    if args.compare:
        verify(args.compare)
        names = read(args.run / 'manifest.json')['outputs'].keys()
        for name in names:
            if name.endswith('.json') and read(args.run / name) != read(args.compare / name):
                raise ValueError('replay_changed: ' + name)
            if name.endswith('.md') and sha(args.run / name) != sha(args.compare / name):
                raise ValueError('report_replay_changed')
        print('JSON metrics, details and Markdown reports replay identically.')
