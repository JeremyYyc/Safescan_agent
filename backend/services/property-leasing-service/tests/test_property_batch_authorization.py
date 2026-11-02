from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy.orm import Session
from safescan_common.http.errors import ApiError

from app.domain.principal import Principal
from app.schemas.commands import PropertyAccessBatchCheck
from app.services.leasing_service import LeasingService
from app.models.tables import Building, Property


def test_batch_checks_direct_and_building_scopes_and_validity_in_one_query():
    # Only columns needed by the production authorization query are required.
    metadata = sa.MetaData()
    properties = sa.Table("properties", metadata,
                          sa.Column("id", sa.Integer, primary_key=True),
                          sa.Column("public_id", sa.Uuid), sa.Column("building_id", sa.Integer),
                          sa.Column("city_id", sa.Text))
    scopes = []
    for name, resource in [("staff_property_scopes", "property_id"),
                           ("staff_building_scopes", "building_id")]:
        scopes.append(sa.Table(name, metadata,
                               sa.Column("id", sa.Integer, primary_key=True),
                               sa.Column("staff_id", sa.Uuid), sa.Column(resource, sa.Integer),
                               sa.Column("valid_from", sa.DateTime(timezone=True)),
                               sa.Column("valid_until", sa.DateTime(timezone=True))))
    engine = sa.create_engine("sqlite://", execution_options={
        "schema_translate_map": {"property_leasing": None}
    })
    metadata.create_all(engine)
    staff_id, subject_id, outsider = uuid4(), uuid4(), uuid4()
    ids = [uuid4() for _ in range(7)]
    now = datetime.now(UTC)
    with Session(engine) as db:
        db.execute(properties.insert(), [{"id": index, "public_id": value,
                                          "building_id": index, "city_id": "sydney"}
                                         for index, value in enumerate(ids)])
        db.execute(scopes[0].insert(), [
            {"id": 1, "staff_id": staff_id, "property_id": 0,
             "valid_from": now - timedelta(days=1), "valid_until": None},
            {"id": 2, "staff_id": staff_id, "property_id": 2,
             "valid_from": now - timedelta(days=2), "valid_until": now - timedelta(days=1)},
            {"id": 3, "staff_id": outsider, "property_id": 3,
             "valid_from": now - timedelta(days=1), "valid_until": None},
            {"id": 4, "staff_id": staff_id, "property_id": 4,
             "valid_from": now + timedelta(days=1), "valid_until": None},
        ])
        db.execute(scopes[1].insert(), [
            {"id": 1, "staff_id": staff_id, "building_id": 1,
             "valid_from": now - timedelta(days=1), "valid_until": now + timedelta(days=1)},
            {"id": 2, "staff_id": staff_id, "building_id": 5,
             "valid_from": now - timedelta(days=2), "valid_until": now - timedelta(days=1)},
            {"id": 3, "staff_id": staff_id, "building_id": 6,
             "valid_from": now - timedelta(days=1), "valid_until": None},
        ])
        db.execute(properties.update().where(properties.c.id == 6).values(city_id="melbourne"))
        actor = Principal(subject_id=subject_id, staff_id=staff_id,
                          account_type="staff", scopes=frozenset(), claims={})
        calls = []
        sa.event.listen(engine, "before_cursor_execute", lambda *args: calls.append(args[2]))
        missing = uuid4()
        identity = Mock()
        identity.get_subject.return_value = {"status": "active", "employment_status": "active",
                                             "staff_id": str(staff_id), "city_id": "sydney"}
        result = LeasingService(db, identity, Mock()).property_authorizations(actor, {
            "subject_id": subject_id, "property_ids": ids + [missing] + ids[:1],
            "action": "maintenance:read_assigned",
        })
        assert result["items"] == [{"property_id": str(value), "allowed": index < 2}
                                   for index, value in enumerate(ids + [missing])]
        assert len(calls) == 1
        city_only = LeasingService(db, identity, Mock()).property_authorizations(actor, {
            "subject_id": subject_id, "property_ids": ids, "action": "city:check",
        })
        assert city_only["items"] == [{"property_id": str(value), "allowed": index < 6}
                                      for index, value in enumerate(ids)]
        identity.get_subject.return_value["city_id"] = "melbourne"
        transferred = LeasingService(db, identity, Mock()).property_authorizations(actor, {
            "subject_id": subject_id, "property_ids": ids, "action": "maintenance:read_assigned",
        })
        assert transferred["items"] == [{"property_id": str(value), "allowed": index == 6}
                                         for index, value in enumerate(ids)]
        assert len(calls) == 3


@pytest.mark.parametrize("account_type,wrong_subject,action", [
    ("customer", False, "maintenance:read_assigned"),
    ("staff", True, "maintenance:read_assigned"),
    ("staff", False, "maintenance:assign_assigned"),
])
def test_batch_rejects_actor_or_action_mismatch_before_database(account_type, wrong_subject, action):
    actor = Principal(subject_id=uuid4(), staff_id=uuid4(), account_type=account_type,
                      scopes=frozenset(), claims={})
    db = Mock()
    with pytest.raises(ApiError) as caught:
        LeasingService(db, Mock(), Mock()).property_authorizations(actor, {
            "subject_id": uuid4() if wrong_subject else actor.subject_id,
            "property_ids": [uuid4()], "action": action,
        })
    assert caught.value.status_code == 403
    db.scalars.assert_not_called()


def test_batch_request_is_bounded_and_action_is_specific():
    data = {"subject_id": uuid4(), "property_ids": [uuid4()] * 201,
            "action": "maintenance:read_assigned"}
    PropertyAccessBatchCheck(**data)
    with pytest.raises(ValidationError):
        PropertyAccessBatchCheck(**{**data, "property_ids": [uuid4()] * 202})
    with pytest.raises(ValidationError):
        PropertyAccessBatchCheck(**{**data, "action": "property:manage_all"})


def test_context_projection_only_queries_authorized_ids_and_keeps_minimal_fields():
    actor = Principal(subject_id=uuid4(), staff_id=uuid4(), account_type="staff",
                      scopes=frozenset(), claims={})
    allowed, denied = uuid4(), uuid4()
    db = Mock()
    building = Building(public_id=uuid4(), name="Harbour House", address="Harbour Road")
    prop = Property(public_id=allowed, reference="P-1", address="Unit 101",
                    attributes={"room_number": "101", "private_note": "not-public"})
    db.execute.return_value.all.return_value = [(prop, building)]
    service = LeasingService(db, Mock(), Mock())
    service.property_authorizations = Mock(return_value={"items": [
        {"property_id": str(allowed), "allowed": True},
        {"property_id": str(denied), "allowed": False},
    ]})
    result = service.property_context_batch(actor, [allowed, denied])
    assert result["items"] == [{"id": str(allowed), "reference": "P-1", "address": "Unit 101",
                                "attributes": {"room_number": "101"},
                                "building": {"id": str(building.public_id), "name": "Harbour House",
                                             "address": "Harbour Road"}}]
    statement = db.execute.call_args.args[0]
    assert list(statement.compile().params.values()) == [[allowed]]
    db.execute.assert_called_once()
