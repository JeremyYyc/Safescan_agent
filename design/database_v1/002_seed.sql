-- Synthetic data only. Run after 001_schema.sql in an isolated database.
BEGIN;
SET LOCAL search_path TO identity_access, property_leasing, maintenance, inspection_report, knowledge, staff_agent;
INSERT INTO organizations(id,name,code) VALUES (1,'Safescan 模拟物业公司','demo'),(2,'隔离组织','isolation');
INSERT INTO staff(id,organization_id,staff_code,display_name) VALUES
 (1,1,'staff_amy','Amy Chen'),(2,1,'staff_ben','Ben Li'),(3,1,'staff_chloe','Chloe Wang'),(4,1,'staff_david','David Liu'),(5,2,'staff_other','Other');
INSERT INTO roles(id,organization_id,code,name) VALUES
 (1,1,'property_manager','物业经理'),(2,1,'leasing_consultant','租赁顾问'),(3,1,'operations_admin','运营管理员');
INSERT INTO permissions(id,organization_id,code,description) VALUES
 (1,1,'property:read','房源详情'),(2,1,'lease:read','租约查询'),(3,1,'rent:read','租金查询'),
 (4,1,'maintenance:read','维修查询'),(5,1,'maintenance:draft','模拟草稿'),
 (6,1,'inspection:read','检查查询'),(7,1,'condition_report:read','房况报告查询'),
 (8,1,'portfolio_metrics:read','组织汇总'),(9,1,'policy:read','政策查询'),
 (10,1,'property:read_summary','房源汇总'),(11,1,'application:read','申请查询，尚未实现');
INSERT INTO staff_roles(organization_id,staff_id,role_id) VALUES (1,1,1),(1,2,1),(1,3,2),(1,4,3);
INSERT INTO role_permissions(organization_id,role_id,permission_id)
 SELECT 1,1,id FROM permissions WHERE organization_id=1 AND id BETWEEN 1 AND 7;
INSERT INTO role_permissions(organization_id,role_id,permission_id) VALUES
 (1,2,1),(1,2,6),(1,2,11),(1,3,8),(1,3,9),(1,3,10);
INSERT INTO properties(id,organization_id,reference,address,bedrooms,bathrooms,weekly_rent,status) VALUES
 (1,1,'HV-101','模拟地址 101',2,1,650,'available'),(2,1,'HV-102','模拟地址 102',3,2,850,'occupied'),
 (3,1,'PA-201','模拟地址 201',2,2,720,'occupied'),(4,2,'OTHER-001','隔离测试地址',1,1,400,'available');
INSERT INTO staff_property_scopes(organization_id,staff_id,property_id) VALUES
 (1,1,1),(1,1,2),(1,2,3),(1,3,1),(1,3,3),(2,5,4);
INSERT INTO parties(id,organization_id,kind,name) VALUES
 (1,1,'owner','模拟业主'),(2,1,'tenant','模拟租客'),(3,1,'vendor','模拟维修商');
INSERT INTO property_owners(organization_id,property_id,party_id,share) VALUES (1,2,1,1);
INSERT INTO leases(id,organization_id,property_id,reference,starts_on,ends_on,weekly_rent,status)
 VALUES(1,1,2,'LEASE-HV102-01','2026-01-01','2026-12-31',850,'active');
INSERT INTO lease_tenants(organization_id,lease_id,party_id) VALUES(1,1,2);
INSERT INTO rent_invoices(id,organization_id,lease_id,reference,due_on,period_start,period_end,amount)
 VALUES(1,1,1,'INV-HV102-09','2026-09-01','2026-09-01','2026-09-07',850);
INSERT INTO payments(id,organization_id,reference,received_at,amount) VALUES(1,1,'PAY-001','2026-09-02T08:00:00Z',500);
INSERT INTO payment_allocations(organization_id,payment_id,invoice_id,amount) VALUES(1,1,1,500);
INSERT INTO maintenance_orders(id,organization_id,property_id,reference,summary,priority,status,assigned_staff_id,vendor_id)
 VALUES(1,1,2,'MAINT-HV102-01','模拟厨房漏水','high','in_progress',1,3);
INSERT INTO maintenance_events(organization_id,order_id,actor_staff_id,event_type,details)
 VALUES(1,1,1,'assigned','{"note":"模拟分配维修商"}');
INSERT INTO inspections(id,organization_id,property_id,inspector_id,kind,inspected_at,status,summary)
 VALUES(1,1,2,1,'routine','2026-09-01T02:00:00Z','completed','厨房发现漏水');
INSERT INTO inspection_findings(organization_id,inspection_id,area,description,severity)
 VALUES(1,1,'厨房','水槽下方有渗水','high');
INSERT INTO knowledge_bases(id,organization_id,code,name,retrieval_provider)
 VALUES(1,1,'staff_policy','员工制度库','mock');
INSERT INTO knowledge_role_access(organization_id,knowledge_base_id,role_id) VALUES(1,1,1),(1,1,2),(1,1,3);
INSERT INTO knowledge_documents(organization_id,knowledge_base_id,document_key,version,title,status)
 VALUES(1,1,'privacy',1,'模拟员工隐私保护制度','published');
INSERT INTO agent_definitions(id,organization_id,code,version,transport,capabilities,enabled)
 VALUES(1,1,'staff_intent','0.1.0','local','["intent_classification","task_split"]',true),
 (2,1,'record_query','0.1.0','local','["read_records"]',false);
INSERT INTO prompt_versions(id,organization_id,agent_id,version,content,sha256)
 VALUES(1,1,1,'seed-placeholder','占位：接入时由 intent_agent.PROMPT 及实际 SHA256 替换','not-a-production-hash');
INSERT INTO staff_sessions(id,organization_id,staff_id,title) VALUES(1,1,1,'模拟员工会话');
INSERT INTO staff_requests(id,organization_id,session_id,original_text,idempotency_key,route,status,route_reason)
 VALUES(1,1,1,'查询 HV-102 的维修状态','mock-request-1','execute','planned','VALIDATED_PLAN'),
 (2,1,1,'查询 HV-102 的维修状态；创建 HV-102 的漏水维修草稿','mock-request-2','human','needs_review','MULTI_TASK_WITH_ACTION');
INSERT INTO intent_runs(id,organization_id,request_id,prompt_id,model,attempt,status,raw_output)
 VALUES(1,1,1,1,'mock-keyword-v1',1,'ok','{"fixture":true}');
INSERT INTO staff_tasks(id,organization_id,request_id,intent_run_id,task_key,ordinal,source_text,span_start,span_end,intent,business_domain)
 VALUES(1,1,1,1,'t1',1,'查询 HV-102 的维修状态',0,15,'record_query','maintenance');
INSERT INTO human_cases(organization_id,request_id,reason) VALUES(1,2,'多任务包含操作；本次不执行任何业务子任务，未提交外部人工队列');
INSERT INTO parties(id,organization_id,kind,name) VALUES(4,1,'prospect','模拟潜在租客');
UPDATE properties SET listing_visibility='public' WHERE organization_id=1 AND id=1;
INSERT INTO tenancy_applications(organization_id,property_id,applicant_id,reference)
 VALUES(1,1,4,'APP-DEMO-001');
INSERT INTO viewing_appointments(organization_id,property_id,prospect_id,host_staff_id,starts_at,ends_at,idempotency_key)
 VALUES(1,1,4,1,'2026-09-10T02:00:00Z','2026-09-10T02:30:00Z','viewing-demo-001');
INSERT INTO property_favorites(organization_id,party_id,property_id) VALUES(1,4,1);
-- Reset identities after explicit demo IDs; do not leave future inserts colliding.
DO $$ DECLARE r record; n bigint; BEGIN
 FOR r IN SELECT table_schema, table_name FROM information_schema.columns WHERE table_schema IN ('identity_access','property_leasing','maintenance','inspection_report','knowledge','staff_agent') AND column_name='id' AND is_identity='YES' LOOP
  EXECUTE format('SELECT max(id) FROM %I.%I',r.table_schema,r.table_name) INTO n;
  IF n IS NOT NULL THEN PERFORM setval(pg_get_serial_sequence(r.table_schema||'.'||r.table_name,'id'),n,true); END IF;
 END LOOP;
END $$;
COMMIT;
