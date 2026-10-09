"""Collect a bounded supplementary batch using the existing public API pipeline."""
import argparse
from pathlib import Path
import indoor_repair_collect as collector

collector.ROOT = Path('data/collection-pilot/used-fixtures-20261009')
collector.QUERIES = {
    'light_fault': ('灯具异常', 'ceiling light flickering'),
    'washer_fault': ('洗衣机异常', 'washing machine not working'),
    'toilet_fault': ('马桶异常', 'toilet not flushing'),
}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['discover', 'download', 'export'])
    parser.add_argument('--toilets', action='store_true')
    args = parser.parse_args()
    if args.toilets:
        collector.ROOT = Path('data/collection-pilot/used-toilets-20261009')
        collector.QUERIES = {'toilet_fault': ('马桶异常', 'toilet running')}
    getattr(collector, args.phase)()
