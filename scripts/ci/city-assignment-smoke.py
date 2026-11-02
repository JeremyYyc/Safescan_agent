#!/usr/bin/env python3
"""Read-only city isolation checks against the local demo's seeded accounts."""
import importlib.util
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

spec = importlib.util.spec_from_file_location('portal_smoke', Path(__file__).with_name('portal-bff-api-smoke.py'))
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
request, expect = module.request, module.expect


def main(base):
    names = [('Noah','Mitchell','sydney'), ('Emma','Collins','melbourne'),
             ('James','Parker','brisbane'), ('Ava','Richardson','adelaide'),
             ('Isabella','Brooks','perth')]
    def login(first,last):
        result = expect(request(base,'POST','/api/v1/auth/login',payload={
            'email': f'{first}Safescan@outlook.com', 'password': f'staff{first}{last}123456'}),200)
        return result['data']['access_token']
    admin = login('Charlotte','Morgan')
    def properties(token):
        items, cursor = [], None
        while True:
            query = {'limit':100}
            if cursor: query['cursor'] = cursor
            result = expect(request(base,'GET','/api/v1/staff/properties?'+urlencode(query),token=token),200)
            items.extend(result['data']['items'])
            cursor = result['data'].get('next_cursor') or result.get('meta',{}).get('next_cursor')
            if not cursor: return items
    all_properties = properties(admin)
    assert len(all_properties) == 508
    summary = {}
    for first,last,city in names:
        token = login(first,last)
        bootstrap = expect(request(base,'GET','/api/v1/staff/bootstrap',token=token),200)
        assert bootstrap['data']['staff']['city_id'] == city
        local = properties(token)
        assert local and all(p.get('city_id') == city for p in local)
        remote = next(p for p in all_properties if p.get('city_id') != city)
        assert request(base,'GET','/api/v1/staff/properties/'+remote['id'],token=token).status == 404
        summary[city] = len(local)
    print(json.dumps({'admin_properties':len(all_properties), 'manager_properties':summary,
                      'cross_city_detail_access':'denied'},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8080')
