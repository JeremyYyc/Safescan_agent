"""The city extension uses the same idempotent Identity seed as existing employees."""
import os

import pytest
import sqlalchemy as sa
from pydantic import SecretStr
from sqlalchemy.orm import sessionmaker

from app import seed_staff
from app.core.config import Settings
from app.core.security import verify_password
from safescan_common.cities import STAFF_CITIES


@pytest.mark.postgres_integration
def test_city_staff_seed_creates_missing_accounts_without_resetting_existing_users(monkeypatch):
    value = os.getenv('TEST_DATABASE_URL')
    if not value:
        pytest.skip('TEST_DATABASE_URL is required')
    url = sa.engine.make_url(value)
    assert 'test' in url.database.split('_')
    engine = sa.create_engine(url)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(seed_staff, 'get_session_factory', lambda: factory)
    monkeypatch.setattr(seed_staff, 'get_settings', lambda: Settings(
        app_env='ci', database_url=SecretStr(value), seed_staff=True,
        jwt_secret=SecretStr('staff-seed-test-secret-at-least-24-characters')))
    codes = [row[0] for row in seed_staff.STAFF_SEEDS]
    query = sa.text('''SELECT s.staff_code,
        md5(to_jsonb(s)::text || to_jsonb(u)::text || to_jsonb(c)::text) AS fingerprint
        FROM identity_access.staff s JOIN identity_access.users u ON u.id=s.user_id
        JOIN identity_access.user_credentials c ON c.user_id=u.id
        WHERE s.staff_code IN :codes''').bindparams(sa.bindparam('codes', expanding=True))
    with engine.connect() as connection:
        before = dict(connection.execute(query, {'codes':codes}).all())
    created = seed_staff.seed()
    assert created == len(codes) - len(before)
    with engine.connect() as connection:
        first = dict(connection.execute(query, {'codes':codes}).all())
        for code in before:
            assert first[code] == before[code], f'Existing employee changed: {code}'
        people = connection.execute(sa.text('''SELECT s.staff_code,s.city_id,s.display_name,
            s.employment_status,u.status,u.username,u.email,r.code AS role,c.algorithm,c.secret_hash
            FROM identity_access.staff s JOIN identity_access.users u ON u.id=s.user_id
            JOIN identity_access.roles r ON r.id=s.role_id
            JOIN identity_access.user_credentials c ON c.user_id=u.id
            WHERE s.staff_code IN :codes''').bindparams(sa.bindparam('codes', expanding=True)),
            {'codes':codes}).mappings().all()
        assert len(people) == 16
        assert {(p['city_id'],p['role']) for p in people if p['role']!='manager_admin'} == {
            (city,role) for city in ('sydney','melbourne','brisbane','adelaide','perth')
            for role in ('leasing_consultant','property_manager','maintainer')}
        for person in people:
            assert person['city_id'] == STAFF_CITIES.get(person['staff_code'])
            assert person['employment_status'] == person['status'] == 'active'
            assert person['algorithm'] == 'argon2id'
            if person['staff_code'] not in before:
                assert verify_password(person['secret_hash'], seed_staff.initial_password(person['username']))
    assert seed_staff.seed() == 0
    with engine.connect() as connection:
        second = dict(connection.execute(query, {'codes':codes}).all())
        assert second == first
    engine.dispose()
