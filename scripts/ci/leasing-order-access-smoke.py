#!/usr/bin/env python3
"""Verify local seeded staff access through Gateway against read-only DB expectations.

Run inside the Property Leasing container (database credentials stay in its env).
--capture writes row fingerprints only; normal verification never writes business data.
Login/logout creates and revokes only the verification sessions.
"""

import argparse
from contextlib import contextmanager
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


def fingerprint(db):
    tables = db.execute("""SELECT schemaname, tablename FROM pg_tables
        WHERE (schemaname='property_leasing' AND tablename<>'outbox_events') OR
        (schemaname='identity_access' AND tablename IN
         ('staff','staff_role_history','roles','role_permissions','permissions','cities'))
        ORDER BY schemaname,tablename""").fetchall()
    result = {}
    for table in tables:
        name = table['schemaname'] + '.' + table['tablename']
        rows = db.execute(sql.SQL("SELECT to_jsonb(t)::text AS row FROM {} t ORDER BY 1").format(
            sql.Identifier(table['schemaname'], table['tablename']))).fetchall()
        digest = hashlib.sha256()
        for row in rows:
            digest.update(row['row'].encode())
            digest.update(b'\n')
        result[name] = {'count': len(rows), 'sha256': digest.hexdigest()}
    return result


@contextmanager
def login(base, staff):
    cookies = http.cookiejar.CookieJar()
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                        urllib.request.HTTPCookieProcessor(cookies))
    token = None

    def request(path, body=None, headers=None):
        headers = {'Content-Type': 'application/json', **(headers or {})}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        req = urllib.request.Request(base + path, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with client.open(req, timeout=30) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    status, raw = request('/api/v1/auth/login', {
        'email': staff['email'], 'password': 'staff' + staff['username'] + '123456',
        'device_label': 'Leasing access regression verification'})
    assert status == 200, (staff['staff_code'], 'login', status)
    token = json.loads(raw)['data']['access_token']
    try:
        yield request
    finally:
        csrf = next((c.value for c in cookies if 'csrf' in c.name.lower()), '')
        status, _ = request('/api/v1/auth/logout', {}, {'X-CSRF-Token': csrf})
        assert status == 204, (staff['staff_code'], 'logout', status)


def read_page(request, path, **params):
    status, raw = request(path + '?' + urllib.parse.urlencode(params))
    assert status == 200, (path, status)
    return json.loads(raw)['data']


def check_pages(request, path, expected, **filters):
    seen, cursor, pages = set(), None, 0
    while True:
        params = {'limit': 50, **filters}
        if cursor:
            params['cursor'] = cursor
        page = read_page(request, path, **params)
        assert page['total'] == len(expected), ('total', page['total'], len(expected))
        ids = [item['id'] for item in page['items']]
        assert len(set(ids)) == len(ids) and not seen.intersection(ids), 'duplicate page rows'
        seen.update(ids)
        pages += 1
        cursor = page.get('next_cursor') or page.get('nextCursor')
        assert pages <= 50, 'pagination did not terminate'
        if not cursor:
            break
    assert seen == expected, ('assignment mismatch', len(seen - expected), len(expected - seen))
    return pages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--base-url', default='http://gateway')
    args = parser.parse_args()
    database_url = os.environ['PROPERTY_LEASING_DATABASE_URL'].replace('postgresql+psycopg:', 'postgresql:')
    with psycopg.connect(database_url, row_factory=dict_row, options='-c default_transaction_read_only=on') as db:
        before = fingerprint(db)
        if args.capture:
            args.capture.write_text(json.dumps(before, indent=2) + '\n')
            print(json.dumps({'captured_tables': len(before)}))
            return
        assert args.baseline, '--baseline is required for verification'
        baseline = json.loads(args.baseline.read_text())
        # Retry counters and delivery timestamps change continuously in a live
        # outbox worker; they are operational state, not order history.
        baseline.pop('property_leasing.outbox_events', None)
        assert before == baseline, 'business data changed before verification'
        staff = db.execute("""SELECT s.public_id,s.staff_code,s.city_id,s.display_name,u.email,u.username,r.code AS role
            FROM identity_access.staff s JOIN identity_access.users u ON u.id=s.user_id
            JOIN identity_access.roles r ON r.id=s.role_id
            WHERE r.code IN ('leasing_consultant','manager_admin')
            AND s.employment_status='active' AND u.status='active' ORDER BY s.staff_code""").fetchall()
        leases = db.execute("""SELECT l.public_id::text AS id,l.status,p.city_id,p.public_id::text AS property_id,
            c.assigned_consultant_staff_id AS staff_id,l.reference,p.reference AS property_reference,
            p.address,p.attributes->>'room_number' AS room_number,b.name AS building_name,
            t.name AS tenant_name,t.contact->>'email' AS tenant_email FROM property_leasing.leases l
            JOIN property_leasing.tenancy_applications a ON a.id=l.application_id
            JOIN property_leasing.prospect_cases c ON c.id=a.prospect_case_id
            JOIN property_leasing.properties p ON p.id=l.property_id
            LEFT JOIN property_leasing.buildings b ON b.id=p.building_id
            JOIN property_leasing.lease_tenants lt ON lt.lease_id=l.id
            JOIN property_leasing.parties t ON t.id=lt.party_id""").fetchall()
        assert len([s for s in staff if s['role'] == 'leasing_consultant']) == 5
        results = []
        for person in staff:
            admin = person['role'] == 'manager_admin'
            own = leases if admin else [l for l in leases if
                l['staff_id'] == person['public_id'] and l['city_id'] == person['city_id']]
            expected = {lease['id'] for lease in own}
            with login(args.base_url, person) as request:
                pages = check_pages(request, '/api/v1/staff/orders', expected)
                check_pages(request, '/api/v1/staff/leases', expected)
                for state in ('active', 'ended', 'executed', 'draft'):
                    check_pages(request, '/api/v1/staff/orders',
                                {l['id'] for l in own if l['status'] == state}, status=state)
                check_pages(request, '/api/v1/staff/orders',
                            {l['id'] for l in own if l['status'] in ('active', 'executed')},
                            status='executed,active')
                search_checks = 0
                if own:
                    fields = ('reference', 'property_reference', 'address', 'room_number',
                              'building_name', 'tenant_name', 'tenant_email')
                    terms = (own[0]['reference'].lower(), own[0]['property_reference'],
                             own[0]['room_number'], own[0]['building_name'], own[0]['tenant_email'],
                             'sim-au26-31', '%', '_', 'no-such-order-xyz')
                    for term in dict.fromkeys(value for value in terms if value):
                        matching = {l['id'] for l in own if any(
                            term.casefold() in str(l.get(field) or '').casefold() for field in fields)}
                        check_pages(request, '/api/v1/staff/orders', matching, q=' ' + term + ' ')
                        search_checks += 1
                    exact = own[0]['reference']
                    check_pages(request, '/api/v1/staff/orders',
                                {l['id'] for l in own if l['reference'] == exact and l['status'] == 'ended'},
                                q=exact, status='ended')
                    status, _ = request('/api/v1/staff/orders?' + urllib.parse.urlencode({'q': 'x' * 201}))
                    assert status == 422, ('query length validation', status)
                denied = 0
                if not admin:
                    cursor = None
                    while True:
                        params = {'limit': 100}
                        if cursor:
                            params['cursor'] = cursor
                        page = read_page(request, '/api/v1/staff/properties', **params)
                        for prop in page['items']:
                            current = prop.get('current_lease')
                            assert not current or current['id'] in expected, 'foreign lease in property list'
                        cursor = page.get('next_cursor') or page.get('nextCursor')
                        if not cursor:
                            break
                    for local in (True, False):
                        foreign = next((l for l in leases if l['id'] not in expected
                                        and (l['city_id'] == person['city_id']) == local), None)
                        if not foreign:
                            continue
                        check_pages(request, '/api/v1/staff/orders', set(), q=foreign['reference'])
                        check_pages(request, '/api/v1/staff/orders',
                                    {l['id'] for l in own if l['property_id'] == foreign['property_id']},
                                    property_id=foreign['property_id'])
                        if local:
                            status, raw = request('/api/v1/staff/properties/' + foreign['property_id'])
                            assert status == 200, ('local property', status)
                            current = json.loads(raw)['data']['property'].get('current_lease')
                            assert not current or current['id'] in expected, 'foreign lease in property detail'
                        for suffix in ('', '/document/pdf'):
                            status, _ = request('/api/v1/staff/leases/' + foreign['id'] + suffix)
                            assert status == 404, (person['staff_code'], 'foreign resource', suffix, status)
                            denied += 1
                if own:
                    status, _ = request('/api/v1/staff/leases/' + own[0]['id'])
                    assert status == 200, ('own detail', person['staff_code'], status)
                    status, raw = request('/api/v1/staff/leases/' + own[0]['id'] + '/document/pdf')
                    assert status == 200 and raw.startswith(b'%PDF-'), ('own PDF', person['staff_code'], status)
            item = {'staff_code': person['staff_code'], 'display_name': person['display_name'],
                    'expected': len(expected), 'visible': len(expected), 'pages': pages,
                    'search_queries_verified': search_checks,
                    'foreign_detail_pdf_denials': denied, 'passed': True}
            results.append(item)
            print(json.dumps(item), flush=True)
        # Use a fresh READ COMMITTED statement snapshot after all HTTP reads.
        assert fingerprint(db) == baseline, 'business data changed during verification'
        report = {'passed': True, 'staff': results, 'business_tables_unchanged': len(before),
                  'excluded_operational_tables': ['property_leasing.outbox_events'],
                  'business_table_fingerprints': before}
        if args.report:
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'passed': True, 'business_tables_unchanged': len(before)}))


if __name__ == '__main__':
    main()
