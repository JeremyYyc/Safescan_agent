#!/usr/bin/env python3
"""Compare every staff role summary with live read-only DB grants via Gateway.

Run inside Property Leasing with leasing-order-access-smoke.py beside this file.
Capture --capture before deployment, then verify with --baseline and --report.
Business and authorization queries are read-only; login/logout only changes the
verification sessions. No seeds, role updates or business writes are performed.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import urllib.parse

import psycopg
from psycopg.rows import dict_row

spec = importlib.util.spec_from_file_location('leasing_audit', Path(__file__).with_name('leasing-order-access-smoke.py'))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def fingerprint(db):
    result = audit.fingerprint(db)
    rows = db.execute('SELECT id,public_id,account_type,status,auth_version,version FROM identity_access.users ORDER BY id').fetchall()
    result['identity_access.user_authorization'] = {'count':len(rows),'sha256':hashlib.sha256(
        json.dumps(rows,sort_keys=True,default=str).encode()).hexdigest()}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path)
    parser.add_argument('--baseline',type=Path)
    parser.add_argument('--report',type=Path)
    args = parser.parse_args()
    url = os.environ['PROPERTY_LEASING_DATABASE_URL'].replace('postgresql+psycopg:','postgresql:')
    with psycopg.connect(url,row_factory=dict_row,options='-c default_transaction_read_only=on') as db:
        before = fingerprint(db)
        if args.capture:
            args.capture.write_text(json.dumps(before,indent=2)+'\n')
            print(json.dumps({'captured_tables_and_projections':len(before)}))
            return
        assert args.baseline and before == json.loads(args.baseline.read_text()), 'Authorization/business data changed before verification'
        rows = db.execute("""SELECT s.public_id::text AS id,s.staff_code,s.display_name,r.code AS role,
            array_remove(array_agg(p.code ORDER BY p.code),NULL) AS permissions FROM identity_access.staff s
            JOIN identity_access.roles r ON r.id=s.role_id
            LEFT JOIN identity_access.role_permissions rp ON rp.role_id=r.id
            LEFT JOIN identity_access.permissions p ON p.id=rp.permission_id
            GROUP BY s.public_id,s.staff_code,s.display_name,r.code ORDER BY s.staff_code""").fetchall()
        expected = {row['id']:row for row in rows}
        pages_by_path = {}
        with audit.login('http://gateway',{'staff_code':'MA001','email':'CharlotteSafescan@outlook.com','username':'CharlotteMorgan'}) as request:
            for path in ('/api/v1/iam/staff','/api/v1/staff/admin/staff'):
                seen,cursor,pages = set(),None,0
                while True:
                    params = {'limit':3}
                    if cursor:
                        params['cursor']=cursor
                    status,raw = request(path+'?'+urllib.parse.urlencode(params))
                    assert status==200,(path,status)
                    response=json.loads(raw)
                    items=response['data'] if isinstance(response['data'],list) else response['data']['items']
                    for item in items:
                        assert item['id'] not in seen, 'Duplicate employee across pages'
                        row=expected[item['id']]
                        assert item.get('permissions') == row['permissions'],(row['staff_code'],'permissions mismatch')
                        assert item['role']['code'] == row['role']
                        seen.add(item['id'])
                    pages+=1
                    assert pages<100,'Non-terminating staff pagination'
                    cursor=(response.get('meta') or {}).get('next_cursor') if isinstance(response['data'],list) else response['data'].get('next_cursor')
                    if not cursor:
                        break
                assert seen==set(expected),(path,'Employees missing')
                pages_by_path[path]=pages
            for row in rows:
                status,raw=request('/api/v1/staff/admin/staff/'+row['id'])
                assert status==200,(row['staff_code'],'detail',status)
                assert json.loads(raw)['data']['staff']['permissions']==row['permissions']
        with audit.login('http://gateway',{'staff_code':'LC001','email':'EthanSafescan@outlook.com','username':'EthanCarter'}) as request:
            for path in ('/api/v1/staff/admin/staff','/api/v1/staff/admin/staff/'+rows[0]['id']):
                status,_=request(path)
                assert status==403,('Non-admin gained access',status)
        assert fingerprint(db)==before,'Authorization/business data changed during verification'
        result={'passed':True,'employees_checked':len(rows),'pagination':pages_by_path,
                'staff':[{'staff_code':r['staff_code'],'role':r['role'],'permission_count':len(r['permissions'])} for r in rows],
                'authorization_and_business_fingerprints_unchanged':before,'non_admin_access_denied':True}
        if args.report:
            args.report.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k!='authorization_and_business_fingerprints_unchanged'},indent=2))


if __name__=='__main__':
    main()
