import os
from urllib.error import HTTPError
from urllib.request import ProxyHandler, build_opener
from uuid import uuid4

import pytest
from pydantic import SecretStr

from inspection_report_service.config import Settings
from inspection_report_service.storage import PipelineStorage


ENDPOINT = os.getenv("REPORT_TEST_MINIO_ENDPOINT")
pytestmark = pytest.mark.skipif(
    not (ENDPOINT and os.getenv("REPORT_TEST_DATABASE_URL")),
    reason="REPORT_TEST_MINIO_ENDPOINT and REPORT_TEST_DATABASE_URL are required",
)


def test_private_minio_object_is_only_available_through_authenticated_adapter() -> None:
    access = os.environ["REPORT_TEST_MINIO_ACCESS_KEY"]
    secret = os.environ["REPORT_TEST_MINIO_SECRET_KEY"]
    settings = Settings(
        database_url=SecretStr(os.environ["REPORT_TEST_DATABASE_URL"]),
        jwt_secret=SecretStr("report-test-secret-that-is-long-enough"),
        minio_endpoint=ENDPOINT, minio_access_key=SecretStr(access),
        minio_secret_key=SecretStr(secret), minio_secure=False,
        minio_media_bucket=os.getenv("REPORT_TEST_MINIO_MEDIA_BUCKET", "report-test-media"),
        minio_derived_bucket=os.getenv("REPORT_TEST_MINIO_DERIVED_BUCKET", "report-test-derived"),
    )
    # The report row is created by the PostgreSQL integration fixture command in
    # the real-component gate; keep this test self-contained at SQL level.
    from sqlalchemy import create_engine, text
    engine = create_engine(os.environ["REPORT_TEST_DATABASE_URL"])
    actor, report_public = uuid4(), uuid4()
    with engine.begin() as db:
        report_id = db.execute(text(
            "INSERT INTO inspection_report.reports "
            "(public_id,property_id,created_by_subject_id,created_by_account_type,is_formal,report_kind,source,title,status,schema_version,pipeline_version) "
            "VALUES (:public,:property,:actor,'staff',true,'analysis','video_analysis','MinIO test','draft',1,'deterministic-test-adapter') RETURNING id"
        ), {"public": report_public, "property": uuid4(), "actor": actor}).scalar_one()
    storage = PipelineStorage(settings, report_id, report_public, actor)
    ref = storage.put(b"private evidence", "image/jpeg", name="evidence.jpg")
    assert storage.read(ref) == b"private evidence"
    file_id = ref.rsplit("/", 1)[-1]
    direct = f"http://{ENDPOINT}/{settings.minio_derived_bucket}/reports/{report_public.hex}/{file_id}"
    with pytest.raises(HTTPError) as denied:
        build_opener(ProxyHandler({})).open(direct, timeout=3)
    assert denied.value.code in {401, 403}
    engine.dispose()
