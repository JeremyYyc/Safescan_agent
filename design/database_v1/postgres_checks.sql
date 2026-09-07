-- Run after schema + seed. All test-only mutations are rolled back.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL search_path TO identity_access, property_leasing, maintenance, inspection_report, knowledge, staff_agent;
DO $$ DECLARE n int; BEGIN
 SELECT count(*) INTO n FROM information_schema.tables
 WHERE table_schema IN ('identity_access','property_leasing','maintenance','inspection_report','knowledge','staff_agent') AND table_type='BASE TABLE';
 IF n != 45 THEN RAISE EXCEPTION 'Expected 45 new tables, found %',n; END IF;
 IF (SELECT amount - COALESCE((SELECT sum(amount) FROM payment_allocations WHERE invoice_id=1 AND organization_id=1),0)
     FROM rent_invoices WHERE id=1 AND organization_id=1) != 350 THEN
   RAISE EXCEPTION 'Incorrect synthetic rent balance';
 END IF;
 IF EXISTS(SELECT 1 FROM staff_tasks WHERE request_id=2) THEN
   RAISE EXCEPTION 'Human-routed request must have no executable tasks in this fixture';
 END IF;
 -- Service-local composite FK rejects a cross-organization lease association.
 BEGIN
  INSERT INTO rent_invoices(organization_id,lease_id,reference,due_on,period_start,period_end,amount)
   VALUES(2,1,'bad-cross-org','2026-09-01','2026-09-01','2026-09-07',1);
  RAISE EXCEPTION 'Cross-organization FK should reject';
 EXCEPTION WHEN foreign_key_violation THEN NULL;
 END;
 BEGIN
  INSERT INTO properties(organization_id,reference,address,bedrooms,bathrooms,weekly_rent)
   VALUES(1,'HV-101','duplicate',1,1,1);
  RAISE EXCEPTION 'Property reference uniqueness should reject';
 EXCEPTION WHEN unique_violation THEN NULL;
 END;
 BEGIN
  INSERT INTO maintenance_drafts(organization_id,task_id,property_id,created_by,summary,mode,status,idempotency_key)
   VALUES(1,1,2,1,'bad','mock','submitted','bad-mock');
  RAISE EXCEPTION 'Mock must not be submitted';
 EXCEPTION WHEN check_violation THEN NULL;
 END;
 BEGIN
  INSERT INTO staff_tasks(organization_id,request_id,intent_run_id,task_key,ordinal,source_text,span_start,span_end,intent,business_domain)
   VALUES(1,2,1,'t1',1,'查询',0,2,'record_query','property');
  RAISE EXCEPTION 'Task and intent run must belong to same request';
 EXCEPTION WHEN foreign_key_violation THEN NULL;
 END;
END $$;
INSERT INTO task_runs(id,organization_id,task_id,agent_id,attempt,status) VALUES(900,1,1,2,1,'running');
DO $$ BEGIN
 BEGIN
  INSERT INTO task_runs(organization_id,task_id,agent_id,attempt,status) VALUES(1,1,2,2,'running');
  RAISE EXCEPTION 'Two active attempts should reject';
 EXCEPTION WHEN unique_violation THEN NULL;
 END;
 BEGIN
  INSERT INTO task_results(organization_id,run_id,answer,source,business_persisted)
   VALUES(1,900,'不应成功','mock',true);
  RAISE EXCEPTION 'Mock result must not claim persistence';
 EXCEPTION WHEN check_violation THEN NULL;
 END;
 BEGIN
  INSERT INTO tool_calls(organization_id,run_id,call_key,tool_name,effect,authorization_decision,status)
   VALUES(1,900,'bad','search_maintenance','read','deny','ok');
  RAISE EXCEPTION 'Denied tool must not succeed';
 EXCEPTION WHEN check_violation THEN NULL;
 END;
 BEGIN
  UPDATE human_cases SET submission_status='submitted' WHERE request_id=2;
  RAISE EXCEPTION 'Submission must have receipt and time';
 EXCEPTION WHEN check_violation THEN NULL;
 END;
END $$;
ROLLBACK;
SELECT 'PASS: table count, seed balance, human fixture, scoped FK, unique keys, intent ownership, active run, mock effects, denied tool, human receipt' AS verification;
