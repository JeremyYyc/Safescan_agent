from uuid import uuid4

import pytest

from reassign_historical_leasing_orders import choose_consultant


def test_existing_local_assignment_is_preserved_over_property_preference():
    current = {'public_id': uuid4(), 'staff_code': 'LC001'}
    preferred = {'public_id': uuid4(), 'staff_code': 'LC006'}
    assert choose_consultant([current, preferred], current['public_id'], str(preferred['public_id']), uuid4()) == current


def test_property_preference_and_stable_local_fallback():
    people = [{'public_id': uuid4(), 'staff_code': code} for code in ('LC001', 'LC006')]
    assert choose_consultant(people, uuid4(), str(people[1]['public_id']), uuid4()) == people[1]
    property_id = uuid4()
    assert choose_consultant(people, None, None, property_id) == choose_consultant(people[::-1], None, None, property_id)


def test_no_local_consultant_fails_instead_of_assigning_across_cities():
    with pytest.raises(ValueError, match='No active same-city'):
        choose_consultant([], uuid4(), uuid4(), uuid4())
