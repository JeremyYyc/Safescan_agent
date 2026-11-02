import os
from pathlib import Path

import pytest
import sqlalchemy as sa

from integrate_execution_dataset import city_staff
from reconcile_city_assignments import pick_staff, reconcile, source_cities


def test_same_city_pool_supports_multiple_people_and_no_cross_city_fallback():
    pool = [{'role': 'property_manager', 'city_id': city, 'staff_code': code,
             'employment_status': 'active', 'status': 'active', 'role_status': 'active'}
            for code, city in [('PM001', 'sydney'), ('PM002', 'sydney'), ('PM003', 'melbourne')]]
    selected = {pick_staff(pool, 'property_manager', 'sydney', str(i))['staff_code'] for i in range(30)}
    assert selected == {'PM001', 'PM002'}
    assert pick_staff(pool, 'property_manager', 'perth', 'building') is None
    assert city_staff('PM', 'perth', 'building') == 'PM005'
    assert city_staff('LC', 'perth', 'building') == 'LC005'
    assert city_staff('MT', 'adelaide', 'building') == 'MT004'
    assert city_staff('MT', 'perth', 'building') == 'MT005'
    assert city_staff('PM', 'darwin', 'building') is None
    assert city_staff('PM', 'melbourne', 'building') == 'PM002'


@pytest.mark.skipif(not os.getenv('CITY_DATASET_ROOT') or not os.getenv('TEST_DATABASE_URL'),
                    reason='Requires a disposable DB and the supplied dataset')
def test_existing_data_reconciliation_is_idempotent_and_keeps_ownership_local():
    url = sa.engine.make_url(os.environ['TEST_DATABASE_URL'])
    assert 'test' in url.database.split('_')
    engine = sa.create_engine(url)
    with engine.connect() as c:
        tx = c.begin()
        try:
            mapping = source_cities(Path(os.environ['CITY_DATASET_ROOT']))
            assert len(mapping) == 500 and None not in mapping.values()
            counts = c.execute(sa.text('SELECT count(*) FROM property_leasing.properties')).scalar_one()
            reconcile(c, mapping)
            again = reconcile(c, mapping)
            assert again['changes'] == {}
            assert c.execute(sa.text('SELECT count(*) FROM property_leasing.properties')).scalar_one() == counts
            assert c.execute(sa.text('''SELECT count(*) FROM property_leasing.staff_building_scopes bs
                JOIN identity_access.staff s ON s.public_id=bs.staff_id
                JOIN property_leasing.buildings b ON b.id=bs.building_id
                WHERE (bs.valid_until IS NULL OR bs.valid_until>now())
                AND (s.city_id IS NULL OR b.city_id IS NULL OR s.city_id<>b.city_id)''')).scalar_one() == 0
            assert c.execute(sa.text('''SELECT count(*) FROM maintenance.maintenance_orders o
                JOIN property_leasing.properties p ON p.public_id=o.property_id
                JOIN identity_access.staff s ON s.public_id=o.assigned_staff_id
                WHERE o.status NOT IN ('completed','cancelled')
                AND (s.city_id IS NULL OR p.city_id IS NULL OR s.city_id<>p.city_id)''')).scalar_one() == 0
        finally:
            tx.rollback()
    engine.dispose()
