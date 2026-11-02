#!/usr/bin/env python3
"""Update the existing local order stack without migrations, seeds or env copies.

Build the images in docker-compose.leasing-access.yml first. Existing container
environment values are reused in memory; secrets are never printed or saved.
Default: validate configuration. --apply recreates only the six named services.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
SERVICES = ('identity-access-service', 'property-leasing-service', 'property-leasing-worker',
            'property-leasing-outbox-worker', 'staff-portal-api', 'staff-web')


def tree_hash(root):
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            digest.update(str(path.relative_to(root)).encode() + b'\0' + path.read_bytes())
    return digest.hexdigest()


def verify_sources(config):
    # Check image contents, not mutable image tags or Git revision labels.
    program = """import hashlib,json
from pathlib import Path
def digest(root):
    value=hashlib.sha256()
    for path in sorted(root.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            value.update(str(path.relative_to(root)).encode()+b'\\0'+path.read_bytes())
    return value.hexdigest()
import safescan_common
print(json.dumps({'app':digest(Path('/app/app')),
                  'common':digest(Path(safescan_common.__file__).parent)}))
"""
    common = tree_hash(ROOT / 'backend/packages/safescan-common/src/safescan_common')
    for name in ('identity-access-service', 'property-leasing-service', 'staff-portal-api'):
        image = config['services'][name]['image']
        result = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'python',
                                 image, '-c', program], check=True, capture_output=True, text=True)
        expected = {'app': tree_hash(ROOT / 'backend/services' / name / 'app'), 'common': common}
        assert json.loads(result.stdout) == expected, f'{name}: image differs from checkout; rebuild first'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', default='safescan_agent')
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    names = (*SERVICES, 'db', 'redis', 'minio')
    raw = subprocess.run(['docker', 'inspect', *[f'{args.project}-{name}-1' for name in names]],
                         check=True, capture_output=True, text=True)
    containers = dict(zip(names, json.loads(raw.stdout)))
    envs = {name: dict(item.split('=', 1) for item in data['Config']['Env'] if '=' in item)
            for name, data in containers.items()}
    variables = set(re.findall(r'\$\{([A-Z_][A-Z0-9_]*)', (ROOT / 'docker-compose.yml').read_text()))
    environment = os.environ.copy()
    for values in envs.values():
        environment.update({key: value for key, value in values.items() if key in variables})
    for target, source, key in (
        ('DATABASE_URL', 'property-leasing-service', 'PROPERTY_LEASING_DATABASE_URL'),
        ('AUTH_SECRET', 'staff-portal-api', 'AUTH_SECRET'),
        ('MINIO_ACCESS_KEY', 'minio', 'MINIO_ROOT_USER'),
        ('MINIO_SECRET_KEY', 'minio', 'MINIO_ROOT_PASSWORD'),
    ):
        environment[target] = envs[source][key]
    # Merge this through stdin so Compose can retain the exact existing service
    # configuration without persisting an additional credential file.
    overlay = json.dumps({'services': {name: {'environment': envs[name]} for name in SERVICES}})
    compose = ['docker', 'compose', '--env-file', str(args.env_file.resolve()), '-p', args.project,
               '-f', str(ROOT / 'docker-compose.yml'),
               '-f', str(ROOT / 'docker-compose.leasing-access.yml'), '-f', '-']
    parsed = subprocess.run([*compose, 'config', '--format', 'json'], env=environment,
                            input=overlay, check=True, capture_output=True, text=True)
    config = json.loads(parsed.stdout)
    for name in SERVICES:
        for key, value in envs[name].items():
            assert config['services'][name]['environment'][key] == value, (name, key)
        assert not containers[name]['Mounts'], f'{name}: review existing mounts before replacing'
    verify_sources(config)
    print('Configuration validated; existing service environments retained.', flush=True)
    if not args.apply:
        return
    subprocess.run([*compose, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never',
                    '--force-recreate', '--wait', '--wait-timeout', '60', *SERVICES],
                   env=environment, input=overlay, text=True, check=True)
    print('Updated only the local order stack; no migrations or data synchronization ran.')


if __name__ == '__main__':
    main()
