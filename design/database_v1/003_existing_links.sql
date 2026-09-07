-- Optional same-service legacy bridge only, after the existing Alembic head.
-- Run in the inspection_report database that owns the legacy public.reports.
-- users and files in other services are logical IDs: intentionally NO cross-service FK.
BEGIN;
ALTER TABLE inspection_report.inspection_reports ADD CONSTRAINT inspection_existing_report_fk
 FOREIGN KEY(report_id) REFERENCES public.reports(id) ON DELETE RESTRICT;
COMMIT;
