from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace

import pytest
from minio.error import S3Error
from pydantic import SecretStr
from pypdf import PdfReader, PdfWriter

from app.core.config import Settings
from app.services import lease_pdf
from app.services.lease_pdf import (LeasePdfStore, jurisdiction_for, render_pdf,
                                    readable_terms, prepare_template, verify_form_values, widget_field)
from app.services.leasing_service import LeasingService
from safescan_common.http.errors import ApiError


def record():
    return {
        "lease_id": "00000000-0000-0000-0000-000000000001", "reference": "L-TEST-1",
        "document_id": "00000000-0000-0000-0000-000000000002", "document_version": 2,
        "document_status": "issued", "document_created_at": "2026-10-01T00:00:00Z",
        "terms_digest": "sha256:" + "a" * 64, "terms_payload": {"term": "Recorded terms"},
        "status": "active", "starts_on": "2026-10-01", "ends_on": "2027-09-30",
        "weekly_rent": "750.00", "currency": "AUD", "property_reference": "P-TEST-1",
        "address": "Unit 1, 10 Harbour Street, Sydney NSW", "building_name": "Harbour House",
        "bedrooms": 2, "bathrooms": "1.5", "parking_spaces": None, "state": "VIC",
        "tenant_name": "Test Renter", "tenant_contact": {"email": "renter@example.test"},
        "occupants": 2, "signatures": [], "synthetic": True,
    }


def blank_template():
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.add_blank_page(width=595, height=842)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_render_includes_personalized_data_and_complete_template_without_mutating_terms():
    source = record()
    before = deepcopy(source)
    pdf = render_pdf(source, blank_template())
    reader = PdfReader(BytesIO(pdf))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert source == before
    assert len(reader.pages) >= 4  # At least two data sheets plus both template pages.
    assert "L-TEST-1" in text and "750.00" in text and "Test Renter" in text
    assert "No signature audit events" in text
    assert "DEMONSTRATION DATA" in text
    assert "not a completed or signed agreement" in " ".join(text.split())
    assert source["terms_digest"] in text.replace("\n", "")


@pytest.mark.parametrize("state", ["NSW", "VIC", "QLD", "WA", "SA"])
def test_jurisdiction_is_explicit_and_never_silently_defaults(state):
    assert jurisdiction_for(f"Unit 2, Example City {state} 2000") == state


def test_jurisdiction_rejects_missing_or_conflicting_state():
    for address, code in (("10 Harbour Street", "lease_jurisdiction_missing"),
                          ("NSW VIC", "lease_jurisdiction_conflict")):
        with pytest.raises(ApiError) as caught:
            jurisdiction_for(address)
        assert caught.value.code == code


def test_jurisdiction_uses_building_timezone_and_rejects_conflicting_address():
    assert jurisdiction_for("298 Pitt Street Sydney 2000", "Australia/Sydney") == "NSW"
    assert jurisdiction_for("5 Example Street", "Australia/Adelaide") == "SA"
    with pytest.raises(ApiError) as caught:
        jurisdiction_for("10 Harbour Street NSW", "Australia/Perth")
    assert caught.value.code == "lease_jurisdiction_conflict"


def test_readable_terms_remove_internal_provenance_and_keep_commercial_terms():
    terms = readable_terms({"dataset": "internal", "source_id": "secret",
                            "source_terms": {"resident_id": "hidden", "weekly_rent": 485,
                                             "occupants": 1, "rent_basis": "property_per_week"}})
    text = str(terms)
    assert "485" in text and "Recorded occupants" in text
    assert "whole property" in text and "secret" not in text and "hidden" not in text


@pytest.mark.parametrize("state", ["NSW", "QLD", "SA"])
def test_actual_official_form_retains_canonical_and_widget_values(state):
    source = record()
    source["state"] = state
    template = (lease_pdf.TEMPLATE_DIR / f"{state.lower()}.pdf").read_bytes()
    content, values = prepare_template(source, template)
    assert len(PdfReader(BytesIO(content)).pages) == len(PdfReader(BytesIO(template)).pages)
    assert source["tenant_name"] in values.values() and "750.00" in values.values()
    assert not any("signature" in key.lower() or "signed" in key.lower() for key in values)
    verify_form_values(PdfReader(BytesIO(content)), values)


@pytest.mark.parametrize("state", ["NSW", "QLD", "SA"])
def test_chinese_tenant_uses_unicode_appearance_and_preserves_real_form_value(state):
    source = record()
    source.update(state=state, tenant_name="模拟住户00020-4")
    template = (lease_pdf.TEMPLATE_DIR / f"{state.lower()}.pdf").read_bytes()
    content, values = prepare_template(source, template)
    reader = PdfReader(BytesIO(content))
    verify_form_values(reader, values)
    found = False
    for page in reader.pages:
        for ref in page.get("/Annots", []):
            widget = ref.get_object()
            _, field = widget_field(widget)
            if field.get("/V") == source["tenant_name"]:
                found = True
                appearance = widget["/AP"]["/N"]
                assert "/Resources" in appearance
                fonts = appearance["/Resources"]["/Font"]
                assert any(font.get_object().get("/Subtype") == "/TrueType"
                           and "/FontFile2" in font.get_object()["/FontDescriptor"]
                           for font in fonts.values())
    assert found
    final = PdfReader(BytesIO(render_pdf(source, template)))
    verify_form_values(final, values)


def test_store_is_idempotent_and_new_signature_creates_new_copy(tmp_path, monkeypatch):
    (tmp_path / "vic.pdf").write_bytes(blank_template())
    monkeypatch.setattr(lease_pdf, "TEMPLATE_DIR", tmp_path)

    class Storage:
        def __init__(self):
            self.objects = {}

        def stat_object(self, bucket, key):
            if key not in self.objects:
                raise S3Error(response=None, code="NoSuchKey", message="missing", resource="resource",
                              request_id="request", host_id="host")

        def bucket_exists(self, bucket):
            return True

        def put_object(self, bucket, key, stream, size, **kwargs):
            self.objects[key] = (stream.read(), kwargs)
            assert len(self.objects[key][0]) == size

    client = Storage()
    settings = Settings(database_url=SecretStr("unused"), jwt_secret=SecretStr("unused"))
    store = LeasePdfStore(settings, client)
    source = record()
    key, created = store.ensure(source)
    assert created and client.objects[key][1]["content_type"] == "application/pdf"
    assert store.ensure(source) == (key, False)
    source["signatures"].append({"side": "tenant", "occurred_at": "2026-10-01T00:00:00Z",
                                 "subject_id": "subject", "staff_id": None,
                                 "terms_digest": source["terms_digest"]})
    changed_key, created = store.ensure(source)
    assert created and changed_key != key and len(client.objects) == 2


def test_unauthorized_lease_pdf_never_touches_storage(monkeypatch):
    service = object.__new__(LeasingService)
    service._lease = lambda lease_id: SimpleNamespace(id=1)
    service._lease_access = lambda actor, lease: False
    def no_storage(*args, **kwargs):
        pytest.fail("Storage must not be accessed before lease authorization")
    monkeypatch.setattr(lease_pdf, "LeasePdfStore", no_storage)
    with pytest.raises(ApiError) as caught:
        service.get_document_pdf(object(), object())
    assert caught.value.status_code == 404
