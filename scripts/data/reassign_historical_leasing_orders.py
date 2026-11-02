#!/usr/bin/env python3
"""Repair existing lease case ownership by property city; default is preview only.

Uses DATABASE_URL (or PROPERTY_LEASING_DATABASE_URL). Never rewrites leases,
documents, signature events, application decisions or contract timestamps.
Every reassignment appends an audit event with both old and new staff IDs.
"""

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa


PROTECTED_TABLES = (
    'leases', 'lease_tenants', 'lease_documents', 'lease_signature_events',
    'tenancy_applications', 'properties', 'buildings', 'parties', 'customer_lease_slots',
    'rent_invoices', 'payments', 'payment_allocations', 'prospect_contact_messages',
)


def fingerprints(connection):
    queries = {name: f'SELECT to_jsonb(t)::text AS row FROM property_leasing.{name} t ORDER BY 1'
               for name in PROTECTED_TABLES}
    queries['case_history'] = """SELECT (to_jsonb(t)-'assigned_consultant_staff_id'-'version'-'updated_at')::text
        AS row FROM property_leasing.prospect_cases t ORDER BY 1"""
    queries['thread_history'] = """SELECT (to_jsonb(t)-'assigned_consultant_staff_id'-'updated_at')::text
        AS row FROM property_leasing.prospect_contact_threads t ORDER BY 1"""
    result = {}
    for name, query in queries.items():
        rows = connection.execute(sa.text(query)).scalars().all()
        result[name] = {'count': len(rows), 'sha256': hashlib.sha256(
            '\n'.join(rows).encode()).hexdigest()}
    return result


def choose_consultant(candidates, current_id, preferred_id, property_id):
    by_id = {str(person['public_id']): person for person in candidates}
    for staff_id in (current_id, preferred_id):
        if str(staff_id) in by_id:
            return by_id[str(staff_id)]
    ordered = sorted(candidates, key=lambda person: person['staff_code'])
    if not ordered:
        raise ValueError('No active same-city Leasing Consultant; no changes applied')
    index = int(hashlib.sha256(str(property_id).encode()).hexdigest()[:8], 16) % len(ordered)
    return ordered[index]


def summary(connection):
    return [dict(row) for row in connection.execute(sa.text("""SELECT s.staff_code,s.display_name,s.city_id,
        count(l.id) AS assigned_leases,
        count(l.id) FILTER(WHERE p.city_id=s.city_id) AS same_city_leases
        FROM identity_access.staff s JOIN identity_access.roles r ON r.id=s.role_id
        LEFT JOIN property_leasing.prospect_cases c ON c.assigned_consultant_staff_id=s.public_id
        LEFT JOIN property_leasing.tenancy_applications a ON a.prospect_case_id=c.id
        LEFT JOIN property_leasing.leases l ON l.application_id=a.id
        LEFT JOIN property_leasing.properties p ON p.id=l.property_id
        WHERE r.code='leasing_consultant' GROUP BY s.staff_code,s.display_name,s.city_id
        ORDER BY s.staff_code""")).mappings()]


def reconcile(connection, *, apply=False, expected_changes=None):
    c = connection
    c.execute(sa.text("SELECT pg_advisory_xact_lock(12608026,501)"))
    c.execute(sa.text("SET LOCAL lock_timeout='10s'"))
    c.execute(sa.text("""LOCK TABLE identity_access.staff,identity_access.users,identity_access.roles,
        property_leasing.properties,property_leasing.buildings,property_leasing.prospect_cases,
        property_leasing.tenancy_applications,property_leasing.leases,property_leasing.lease_tenants,
        property_leasing.lease_documents,property_leasing.lease_signature_events,
        property_leasing.prospect_contact_threads,property_leasing.prospect_case_events
        IN SHARE ROW EXCLUSIVE MODE"""))
    before = fingerprints(c)
    before_counts = summary(c)
    mismatches = c.scalar(sa.text("""SELECT count(*) FROM property_leasing.leases l
        JOIN property_leasing.tenancy_applications a ON a.id=l.application_id
        JOIN property_leasing.prospect_cases c ON c.id=a.prospect_case_id
        WHERE l.property_id<>a.property_id OR l.property_id<>c.property_id"""))
    if mismatches:
        raise ValueError('Lease/application/case property mismatch; no changes applied')
    pool = [dict(row) for row in c.execute(sa.text("""SELECT s.public_id,s.staff_code,s.city_id
        FROM identity_access.staff s JOIN identity_access.users u ON u.id=s.user_id
        JOIN identity_access.roles r ON r.id=s.role_id WHERE r.code='leasing_consultant'
        AND r.status='active' AND u.status='active' AND s.employment_status='active'
        AND s.city_id IS NOT NULL""")).mappings()]
    cases = c.execute(sa.text("""SELECT c.id,c.public_id,c.assigned_consultant_staff_id,c.stage,
        p.public_id AS property_id,p.city_id,p.attributes->'consultant'->>'id' AS preferred_id
        FROM property_leasing.prospect_cases c JOIN property_leasing.properties p ON p.id=c.property_id
        WHERE EXISTS(SELECT 1 FROM property_leasing.tenancy_applications a
            JOIN property_leasing.leases l ON l.application_id=a.id WHERE a.prospect_case_id=c.id)
        ORDER BY c.id""")).mappings().all()
    changes = []
    for case in cases:
        if not case['city_id']:
            raise ValueError(f"Case {case['public_id']} has no property city; no changes applied")
        target = choose_consultant([p for p in pool if p['city_id'] == case['city_id']],
                                    case['assigned_consultant_staff_id'],case['preferred_id'],case['property_id'])
        if target['public_id'] != case['assigned_consultant_staff_id']:
            changes.append((case, target))
    if expected_changes is not None and len(changes) != expected_changes:
        raise ValueError(f'Expected {expected_changes} reassignments, found {len(changes)}; no changes applied')
    operation_id = uuid4()
    if apply and changes:
        actor = c.execute(sa.text("""SELECT u.public_id FROM identity_access.staff s
            JOIN identity_access.users u ON u.id=s.user_id JOIN identity_access.roles r ON r.id=s.role_id
            WHERE r.code='manager_admin' AND r.status='active' AND u.status='active'
            AND s.employment_status='active' ORDER BY s.staff_code LIMIT 1""")).scalar_one()
        now = c.scalar(sa.text('SELECT CURRENT_TIMESTAMP'))
        for case, target in changes:
            c.execute(sa.text("""UPDATE property_leasing.prospect_cases
                SET assigned_consultant_staff_id=:target,version=version+1,updated_at=:now WHERE id=:id"""),
                {'target': target['public_id'], 'now': now, 'id': case['id']})
            c.execute(sa.text("""UPDATE property_leasing.prospect_contact_threads
                SET assigned_consultant_staff_id=:target,updated_at=:now WHERE prospect_case_id=:id"""),
                {'target': target['public_id'], 'now': now, 'id': case['id']})
            details = {'reason': 'historical_lease_city_reassignment', 'operation_id': str(operation_id),
                       'from_staff_id': str(case['assigned_consultant_staff_id']) if case['assigned_consultant_staff_id'] else None,
                       'to_staff_id': str(target['public_id']), 'to_staff_code': target['staff_code'],
                       'property_id': str(case['property_id']), 'city_id': case['city_id']}
            c.execute(sa.text("""INSERT INTO property_leasing.prospect_case_events
                (prospect_case_id,sequence_no,event_type,from_stage,to_stage,actor_subject_id,occurred_at,details_redacted)
                SELECT :id,COALESCE(max(sequence_no),0)+1,'consultant_reassigned',:stage,:stage,:actor,:now,CAST(:details AS jsonb)
                FROM property_leasing.prospect_case_events WHERE prospect_case_id=:id"""),
                {'id':case['id'],'stage':case['stage'],'actor':actor,'now':now,'details':json.dumps(details)})
    assert fingerprints(c) == before, 'Contract, signature or historical business content changed; transaction must roll back'
    after_counts = summary(c)
    if apply:
        assert all(row['assigned_leases'] == row['same_city_leases'] for row in after_counts), 'Cross-city orders remain'
    return {'applied': apply,'operation_id': str(operation_id),'cases_reassigned':len(changes),
            'reassignments_by_city':dict(Counter(case['city_id'] for case, _ in changes)),
            'before':before_counts,'after':after_counts,'protected_content_unchanged':True,
            'protected_fingerprints':before}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expected-changes', type=int)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.apply and args.expected_changes is None:
        parser.error('--apply requires --expected-changes from the preview')
    url = os.getenv('DATABASE_URL') or os.environ['PROPERTY_LEASING_DATABASE_URL']
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        report = reconcile(connection,apply=args.apply,expected_changes=args.expected_changes)
    engine.dispose()
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key:value for key,value in report.items() if key!='protected_fingerprints'},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
