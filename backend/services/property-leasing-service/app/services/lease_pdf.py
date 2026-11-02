"""Private, reproducible PDF copies of lease records and their jurisdiction's form.

The signed terms payload/digest is never changed by PDF rendering. The attachment is
the complete government form, rather than a locally invented set of legal clauses.
"""

import hashlib
import json
import re
from datetime import date
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import sqlalchemy as sa
import urllib3
from fastapi.encoders import jsonable_encoder
from minio import Minio
from minio.error import S3Error
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (ArrayObject, BooleanObject, DecodedStreamObject, DictionaryObject,
                          FloatObject, NameObject, TextStringObject)
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.errors import error
from app.models.tables import Application, Building, LeaseDocument, LeaseSignatureEvent, LeaseTenant, Party, Property


TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "resources" / "lease_templates"
FONT_PATH = Path(__file__).resolve().parents[1] / "resources" / "fonts" / "DroidSansFallback.ttf"
FONT_NAME = "LeaseSans"
RENDERER_VERSION = "lease-copy-5"
JURISDICTIONS = {
    "NSW": ("New South Wales", "Standard residential tenancy agreement",
            "https://www.nsw.gov.au/housing-and-construction/rental-forms-surveys-and-data/resources/standard-residential-tenancy-agreement"),
    "VIC": ("Victoria", "Residential rental agreement",
            "https://www.consumer.vic.gov.au/housing/renting/starting-and-changing-rental-agreements/different-rental-agreements/residential-rental-agreements"),
    "QLD": ("Queensland", "General tenancy agreement (Form 18a)",
            "https://www.rta.qld.gov.au/sites/default/files/2021-06/Form-18a-General-tenancy-agreement.pdf"),
    "WA": ("Western Australia", "Residential tenancy agreement (Form 1AA)",
           "https://www.consumerprotection.wa.gov.au/system/files/documents/2026-04/form1AArentalagreement2026.docx"),
    "SA": ("South Australia", "Residential tenancy agreement (fixed term)",
           "https://www.cbs.sa.gov.au/documents/tenancy/forms/Fixed_term_lease_agreement.pdf"),
}


def jurisdiction_for(address: str, timezone: str | None = None) -> str:
    zone_state = {"Australia/Sydney": "NSW", "Australia/Melbourne": "VIC",
                  "Australia/Brisbane": "QLD", "Australia/Perth": "WA",
                  "Australia/Adelaide": "SA"}.get(timezone)
    matches = re.findall(r"\b(NSW|VIC|QLD|WA|SA)\b", address.upper())
    states = set(matches)
    if len(states) > 1 or (states and zone_state and zone_state not in states):
        raise error(409, "lease_jurisdiction_conflict", "Lease state and building timezone disagree")
    if zone_state:
        return zone_state
    if len(states) != 1:
        raise error(409, "lease_jurisdiction_missing",
                    "Lease address must identify one supported Australian state")
    return matches[0]


def build_record(db, lease, document) -> dict:
    prop = db.get(Property, lease.property_id)
    building = db.get(Building, prop.building_id) if prop.building_id else None
    tenant = db.scalar(sa.select(LeaseTenant).where(LeaseTenant.lease_id == lease.id))
    party = db.get(Party, tenant.party_id) if tenant else None
    application = db.get(Application, lease.application_id)
    signatures = list(db.scalars(sa.select(LeaseSignatureEvent).where(
        LeaseSignatureEvent.lease_document_id == document.id).order_by(
            LeaseSignatureEvent.occurred_at, LeaseSignatureEvent.id)))
    address = prop.address
    state = jurisdiction_for(f"{address} {building.address if building else ''}",
                             building.timezone if building else None)
    return jsonable_encoder({
        "lease_id": str(lease.public_id), "reference": lease.reference,
        "document_id": str(document.public_id), "document_version": document.version,
        "document_status": document.status, "document_created_at": document.created_at,
        "terms_digest": document.terms_digest, "terms_payload": document.terms_payload,
        "status": lease.status, "starts_on": lease.starts_on, "ends_on": lease.ends_on,
        "weekly_rent": str(lease.weekly_rent), "currency": lease.currency,
        "property_reference": prop.reference, "address": address,
        "building_name": building.name if building else None,
        "bedrooms": prop.bedrooms, "bathrooms": str(prop.bathrooms),
        "parking_spaces": prop.parking_spaces, "state": state,
        "synthetic": bool((prop.attributes or {}).get("is_synthetic")
                          or (building and (building.attributes or {}).get("is_synthetic"))
                          or (document.terms_payload or {}).get("is_synthetic")),
        "tenant_name": party.name if party else None,
        "tenant_contact": party.contact if party else {},
        "occupants": application.occupants if application else None,
        "signatures": [{"side": s.side, "occurred_at": s.occurred_at,
                        "subject_id": str(s.signer_subject_id) if s.signer_subject_id else None,
                        "staff_id": str(s.signer_staff_id) if s.signer_staff_id else None,
                        "terms_digest": s.terms_digest} for s in signatures],
    })


def readable_terms(payload: dict) -> list[tuple[str, str]]:
    """Present contractual fields without dataset provenance or internal entity IDs."""
    labels = {"starts_on": "Start date", "ends_on": "End date", "weekly_rent": "Weekly rent",
              "occupants": "Recorded occupants", "rent_basis": "Rent basis",
              "signed_at": "Signature date in source record", "ended_at": "End recorded at",
              "reference": "Contract reference", "status": "Recorded status", "currency": "Currency"}
    excluded = {"id", "dataset", "is_synthetic", "simulation_as_of", "source_id"}
    rows = []

    def visit(values: dict, prefix=""):
        for key, value in sorted(values.items()):
            if key in excluded or key.endswith("_id") or key.endswith("_ids"):
                continue
            if key == "source_terms" and isinstance(value, dict):
                visit(value, prefix)
                continue
            label = prefix + labels.get(key, key.replace("_", " ").capitalize())
            if isinstance(value, dict):
                visit(value, label + ": ")
            else:
                if key == "rent_basis" and value == "property_per_week":
                    value = "Rent for the whole property, charged per week"
                elif key == "rent_basis" and value == "room_per_week":
                    value = "Rent for the selected room, charged per week"
                if isinstance(value, list):
                    value = "; ".join(str(item) for item in value if not isinstance(item, dict))
                if value is not None:
                    rows.append((label, str(value)))
    visit(payload)
    return rows


def form_values(record: dict, fields: dict) -> dict[str, str]:
    """Fill only identified fields; never infer signature, bond or statutory declarations."""
    def d(value):
        return date.fromisoformat(value).strftime("%d/%m/%Y")
    contact = record["tenant_contact"]
    if record["state"] == "NSW":
        expected = {
            "Text field 2.6": "Type tenant 1 name",
            "Text field 2.14": "Type contact details",
            "Text field 3.9": "Type agreement start date in dd/mm/yyyy format",
            "Text field 3.10": "Type agreement end date in dd/mm/yyyy format",
            "Text field 3.11": "Type address of residential premises",
            "Text field 3.13": "Type the amount of rent",
            "Text field 3.17": "Type description of payment frequency",
        }
        if any(str((fields.get(k) or {}).get("/TU")) != tip for k, tip in expected.items()):
            raise ValueError("NSW template fields differ from the verified official form")
        values = {"Text field 2.6": record["tenant_name"],
                  "Text field 2.14": ", ".join(str(contact[k]) for k in ("email", "phone") if contact.get(k)),
                  "Text field 3.9": d(record["starts_on"]), "Text field 3.10": d(record["ends_on"]),
                  "Text field 3.11": record["address"], "Text field 3.13": record["weekly_rent"],
                  "Text field 3.17": "week"}
    elif record["state"] == "QLD":
        values = {"Tenant 1 full name/s": record["tenant_name"],
                  "Tenant 1 email": contact.get("email"), "Tenant 1 phone number": contact.get("phone"),
                  "Address of the rental premises1": record["address"],
                  "Start date (dd/mm/yyyy)": d(record["starts_on"]),
                  "End date (dd/mm/yyyy)": d(record["ends_on"]),
                  "Rent amount": record["weekly_rent"], "week, fortnight or month": "week"}
    elif record["state"] == "SA":
        values = {"Insert full name of tenant 1": record["tenant_name"],
                  "Tenant 1's email address for service of notice or documents": contact.get("email"),
                  "Tenant 1's telephone number": contact.get("phone"),
                  "Address of premises": record["address"], "Start date_af_date": d(record["starts_on"]),
                  "End date_af_date": d(record["ends_on"]), "Weekly amount": record["weekly_rent"],
                  "weeklyfortnightlymonthly": "weekly"}
    else:
        return {}
    selected = {key: str(value) for key, value in values.items() if value not in (None, "")}
    missing = set(selected) - set(fields)
    if missing:
        raise ValueError(f"Official template is missing identified fields: {sorted(missing)}")
    return selected


def widget_field(widget) -> tuple[str, dict]:
    """Resolve a fully qualified field, including NSW's parent.child names."""
    names, terminal = [], None
    current = widget
    while current is not None:
        if current.get("/T") is not None:
            names.insert(0, str(current["/T"]))
            if terminal is None:
                terminal = current
        parent = current.get("/Parent")
        current = parent.get_object() if parent else None
    return ".".join(names), terminal if terminal is not None else widget


def verify_form_values(reader, values: dict) -> None:
    fields = reader.get_fields() or {}
    for name, value in values.items():
        if str((fields.get(name) or {}).get("/V")) != value:
            raise ValueError(f"Canonical PDF field did not retain its value: {name}")
    seen = set()
    for page in reader.pages:
        for ref in page.get("/Annots", []):
            widget = ref.get_object()
            if widget.get("/Subtype") != "/Widget":
                continue
            name, source = widget_field(widget)
            if name in values:
                seen.add(name)
                if str(widget.get("/V", source.get("/V"))) != values[name]:
                    raise ValueError(f"PDF widget did not retain its value: {name}")
                if not (widget.get("/AP") or {}).get("/N"):
                    raise ValueError(f"PDF widget has no rendered appearance: {name}")
    if seen != set(values):
        raise ValueError("Filled canonical PDF fields are missing their page widgets")


@lru_cache(maxsize=1)
def register_font() -> None:
    # Embed a TrueType subset; readers need no external Asian language packs.
    pdfmetrics.registerFont(TTFont(FONT_NAME, str(FONT_PATH)))


def unicode_appearances(writer, values: dict) -> None:
    """Give Unicode fields an embedded font instead of the form's Latin encoding.

    The value remains a real, editable AcroForm value. The Form XObject is generated
    from the same Unicode value and has the widget's exact bounding box. Resources
    are cloned into the output writer so no references to the temporary PDF escape.
    """
    register_font()
    for page in writer.pages:
        for ref in page.get("/Annots", []):
            widget = ref.get_object()
            if widget.get("/Subtype") != "/Widget":
                continue
            name, field = widget_field(widget)
            if name not in values:
                continue
            value = values[name]
            field[NameObject("/V")] = TextStringObject(value)
            if "/V" in widget or field is widget:
                widget[NameObject("/V")] = TextStringObject(value)
            rect = [float(x) for x in widget["/Rect"]]
            width, height = rect[2] - rect[0], rect[3] - rect[1]
            text_width = pdfmetrics.stringWidth(value, FONT_NAME, 1)
            size = min(10, height - 4, (width - 4) / max(text_width, 1))
            appearance_pdf = BytesIO()
            canvas = Canvas(appearance_pdf, pagesize=(width, height), pageCompression=1)
            canvas.setFont(FONT_NAME, size)
            canvas.setFillColor(colors.black)
            canvas.drawString(2, max(2, (height - size) / 2 + size * 0.15), value)
            canvas.save()
            appearance_page = PdfReader(BytesIO(appearance_pdf.getvalue())).pages[0]
            appearance = DecodedStreamObject()
            appearance.set_data(appearance_page.get_contents().get_data())
            appearance.update({
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Form"),
                NameObject("/BBox"): ArrayObject([FloatObject(x) for x in (0, 0, width, height)]),
                NameObject("/Resources"): appearance_page["/Resources"].clone(writer),
            })
            widget[NameObject("/AP")] = DictionaryObject({
                NameObject("/N"): writer._add_object(appearance),
            })
    writer.root_object["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(False)


def prepare_template(record: dict, template_bytes: bytes) -> tuple[bytes, dict]:
    reader = PdfReader(BytesIO(template_bytes))
    values = form_values(record, reader.get_fields() or {})
    if not values:
        return template_bytes, {}
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    latin = {key: value for key, value in values.items() if value.isascii()}
    non_latin = {key: value for key, value in values.items() if not value.isascii()}
    if latin:
        writer.update_page_form_field_values(None, latin, auto_regenerate=False)
    if non_latin:
        unicode_appearances(writer, non_latin)
    output = BytesIO()
    writer.write(output)
    content = output.getvalue()
    verify_form_values(PdfReader(BytesIO(content)), values)
    return content, values


def render_pdf(record: dict, template_bytes: bytes) -> bytes:
    """Render data sheets and attach the complete form without changing its clauses."""
    filled_template, values = prepare_template(record, template_bytes)
    register_font()
    styles = getSampleStyleSheet()
    for name in ("Normal", "BodyText", "Heading1", "Heading2", "Title"):
        styles[name].fontName = FONT_NAME
    styles["BodyText"].leading = 15
    styles["BodyText"].spaceAfter = 6
    styles["Heading2"].spaceBefore = 12
    styles["Heading2"].spaceAfter = 7
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=8, leading=11,
                           alignment=TA_LEFT, wordWrap="CJK")
    body = ParagraphStyle("copy-body", parent=styles["BodyText"], fontSize=10, wordWrap="CJK")
    story = []

    def para(value, style=body):
        return Paragraph(escape(str(value if value is not None else "Not recorded")), style)

    def section(title, rows):
        story.append(para(title, styles["Heading2"]))
        table = Table([[para(label, small), para(value)] for label, value in rows],
                      colWidths=[45 * mm, 125 * mm], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.35, colors.HexColor("#d8e1e8")),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(table)

    state, title, source = JURISDICTIONS[record["state"]]
    story.append(para("RESIDENTIAL TENANCY RECORD", styles["Title"]))
    story.append(para(f"{record['reference']} | {state}", styles["Heading2"]))
    if record.get("synthetic"):
        story.append(para("DEMONSTRATION DATA - this record is marked as synthetic in the source database."))
    story.append(para("System-generated display copy. These data sheets reproduce the stored lease "
                      "record and are followed by the complete official standard agreement form. "
                      "Known tenant, premises, dates and rent fields are filled where the form supports them. "
                      "The attached form is partially completed reference material, not a completed or signed agreement. "
                      "Missing information is explicitly identified below. No handwritten signatures "
                      "or unrecorded commercial terms have been created."))
    section("1. Lease and premises", [
        ("Lease status", record["status"]), ("Lease period", f"{record['starts_on']} to {record['ends_on']}"),
        ("Weekly rent", f"{record['currency']} {record['weekly_rent']} per week"),
        ("Property", f"{record['property_reference']} | {record['address']}"),
        ("Building", record["building_name"]), ("Bedrooms / bathrooms", f"{record['bedrooms']} / {record['bathrooms']}"),
        ("Parking spaces", record["parking_spaces"]), ("Occupants", record["occupants"]),
    ])
    contact = record["tenant_contact"]
    section("2. Parties and contact details", [
        ("Renter / tenant", record["tenant_name"]),
        ("Tenant email", contact.get("email")), ("Tenant phone", contact.get("phone")),
        ("Rental provider / lessor", "Not recorded - must be completed by the parties"),
        ("Agent / service address", "Not recorded - must be completed by the parties"),
    ])
    section("3. Information requiring completion", [
        ("Bond / deposit", "Not recorded; no bond amount inferred from weekly rent"),
        ("Rent payment details", "Not recorded; payment method, account and first due date require confirmation"),
        ("Utilities / inclusions", "Not recorded unless expressly included in the stored terms below"),
        ("Condition report", "Separate condition report and statutory disclosures are not attached to this copy"),
        ("Special conditions", "Only recorded supplementary terms below are reproduced; no extra conditions inferred"),
    ])
    terms = readable_terms(record["terms_payload"])
    section("4. Recorded supplementary terms", terms or [("Additional terms", "None recorded")])
    story.append(Spacer(1, 8 * mm))
    section("5. Document identity and signature audit", [
        ("Document UUID", record["document_id"]),
        ("Version / state", f"{record['document_version']} / {record['document_status']}"),
        ("Document created", record["document_created_at"]),
        ("Stored terms digest", record["terms_digest"]),
    ])
    if record["signatures"]:
        for signature in record["signatures"]:
            story.append(para(f"Recorded {signature['side']} signature event: {signature['occurred_at']}", small))
    else:
        story.append(para("No signature audit events are recorded for this document version.", small))
    story.append(para("Audit events are database records and do not reproduce a signed original.", small))
    story.append(para("6. Official agreement form attached", styles["Heading2"]))
    story.append(para(f"{title} - {state}. The following pages reproduce the complete official form. "
                      "Its terms and completion instructions must be read in full. These data sheets "
                      "do not override or complete the statutory form.", small))
    story.append(para(f"Official source: {source}", small))
    story.append(para(f"Template SHA-256: {hashlib.sha256(template_bytes).hexdigest()}", small))
    buffer = BytesIO()

    def footer(canvas, doc):
        canvas.setFont(FONT_NAME, 8)
        canvas.setFillColor(colors.HexColor("#526575"))
        canvas.drawString(20 * mm, 13 * mm, "SafeScan | System-generated display copy")
        canvas.drawRightString(190 * mm, 13 * mm, f"Data sheet {doc.page}")

    SimpleDocTemplate(buffer, pagesize=(210 * mm, 297 * mm), rightMargin=20 * mm,
                      leftMargin=20 * mm, topMargin=18 * mm, bottomMargin=22 * mm,
                      title=f"Lease {record['reference']} - display copy").build(
                          story, onFirstPage=footer, onLaterPages=footer)
    # Preserve the official form's field tree and page widgets as one document.
    # Prepending annotation-free data sheets avoids append()'s link-remapping
    # warning path, which compares widgets against an unfinished target page.
    writer = PdfWriter()
    writer.clone_document_from_reader(PdfReader(BytesIO(filled_template)))
    for index, page in enumerate(PdfReader(BytesIO(buffer.getvalue())).pages):
        writer.insert_page(page, index)
    writer.add_metadata({"/Title": f"Lease {record['reference']} - display copy",
                         "/Subject": f"Document {record['document_id']}, version {record['document_version']}",
                         "/Author": "SafeScan"})
    output = BytesIO()
    writer.write(output)
    result = output.getvalue()
    verify_form_values(PdfReader(BytesIO(result)), values)
    return result


class LeasePdfStore:
    def __init__(self, settings, client=None):
        self.bucket = settings.minio_reports_bucket
        self.client = client or Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key.get_secret_value(),
            secret_key=settings.minio_secret_key.get_secret_value(),
            secure=settings.minio_secure, region=settings.minio_region,
            http_client=urllib3.PoolManager(timeout=urllib3.Timeout(connect=2, read=15), retries=1),
        )

    def ensure(self, record: dict) -> tuple[str, bool]:
        template = (TEMPLATE_DIR / f"{record['state'].lower()}.pdf").read_bytes()
        fingerprint = hashlib.sha256(
            RENDERER_VERSION.encode() + json.dumps(record, sort_keys=True, ensure_ascii=False,
                                                  separators=(",", ":")).encode() + template).hexdigest()
        key = (f"lease-contracts/{record['lease_id']}/{record['document_id']}/"
               f"v{record['document_version']}-{fingerprint}.pdf")
        try:
            self.client.stat_object(self.bucket, key)
            return key, False
        except S3Error as exc:
            if exc.code not in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
                raise
        if not self.client.bucket_exists(self.bucket):
            try:
                self.client.make_bucket(self.bucket)
            except S3Error as exc:
                if exc.code not in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
                    raise
        content = render_pdf(record, template)
        self.client.put_object(self.bucket, key, BytesIO(content), len(content),
                               content_type="application/pdf", metadata={
                                   "sha256": hashlib.sha256(content).hexdigest(),
                                   "document-id": record["document_id"],
                                   "terms-digest": record["terms_digest"],
                                   "renderer": RENDERER_VERSION,
                               })
        return key, True

    def read(self, key: str) -> bytes:
        response = self.client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
