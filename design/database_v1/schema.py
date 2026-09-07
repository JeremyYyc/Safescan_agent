"""Review-only PostgreSQL expansion. Importing this module never connects to a DB."""
from pathlib import Path
from sqlalchemy import (MetaData, Table, Column, BigInteger, Integer, Text, Boolean,
    Date, DateTime, Numeric, Identity, ForeignKeyConstraint, UniqueConstraint,
    CheckConstraint, Index, text)
from sqlalchemy.dialects.postgresql import JSONB, dialect
from sqlalchemy.schema import CreateTable, CreateIndex

metadata = MetaData()
SERVICE_TABLES = {
 'identity_access': 'organizations account_memberships staff roles permissions staff_roles role_permissions',
 'property_leasing': 'properties staff_property_scopes parties property_owners leases lease_tenants rent_invoices payments payment_allocations tenancy_applications viewing_appointments property_favorites',
 'maintenance': 'maintenance_orders maintenance_events maintenance_drafts approval_requests',
 'inspection_report': 'inspections inspection_findings inspection_reports report_jobs report_job_steps',
 'knowledge': 'knowledge_bases knowledge_role_access knowledge_documents',
 'staff_agent': 'agent_definitions prompt_versions staff_sessions staff_requests intent_runs staff_tasks task_dependencies task_runs tool_calls task_results human_cases a2a_delegations outbox_events audit_events',
}
OWNERS = {t: service for service, tables in SERVICE_TABLES.items() for t in tables.split()}
LOGICAL_LINKS = []

def col(name, typ=Text, *, nullable=False, default=None, comment=''):
    return Column(name, typ, nullable=nullable,
                  server_default=text(default) if default is not None else None, comment=comment)

def enum(name, values, default=None):
    return col(name, comment=' / '.join(values), default=repr(default) if default else None)

def ref(name, target, nullable=False):
    return (name, target, nullable)

def table(name, description, *fields, unique=(), checks=(), tenant=True):
    service = OWNERS[name]
    columns = [Column('id', BigInteger, Identity(), primary_key=True),
               col('created_at', DateTime(timezone=True), default='CURRENT_TIMESTAMP')]
    constraints = []
    if tenant:
        columns.append(col('organization_id', BigInteger))
        constraints += [UniqueConstraint('organization_id', 'id')]
        if service == 'identity_access':
            constraints.append(ForeignKeyConstraint(['organization_id'], ['identity_access.organizations.id']))
        else:
            LOGICAL_LINKS.append((name,'organization_id','organizations'))
    for f in fields:
        if isinstance(f, tuple):
            fname, target, nullable = f
            columns.append(col(fname, BigInteger, nullable=nullable))
            if OWNERS[target] == service:
                constraints.append(ForeignKeyConstraint(
                    ['organization_id', fname],
                    [f'{service}.{target}.organization_id', f'{service}.{target}.id']))
            else:
                LOGICAL_LINKS.append((name, fname, target))
        else:
            columns.append(f)
            if f.comment and ' / ' in f.comment:
                values = ','.join(repr(x) for x in f.comment.split(' / '))
                constraints.append(CheckConstraint(f"{f.name} IN ({values})"))
    for keys in unique:
        constraints.append(UniqueConstraint(*(['organization_id'] if tenant else []), *keys))
    constraints.extend(CheckConstraint(c) for c in checks)
    t = Table(name, metadata, *columns, *constraints, schema=service, comment=description)
    for f in fields:
        if isinstance(f, tuple):
            Index(f'ix_{name}_{f[0]}', t.c.organization_id, t.c[f[0]])
    return t

J = JSONB
TS = DateTime(timezone=True)
MONEY = Numeric(14, 2)

table('organizations', '物业运营组织；全部新增业务数据的隔离根',
      col('name'), col('code'), enum('status', ['active','suspended'], 'active'),
      col('timezone', default="'Asia/Shanghai'"), unique=[('code',)], tenant=False)
table('account_memberships', '共享账号在组织中的身份；员工与租客身份可同时存在，角色由服务端验证',
      col('user_id',BigInteger), enum('persona',['staff','tenant','prospect']),
      enum('status',['active','inactive'],'active'), unique=[('user_id','persona')])
table('staff', '员工身份；user_id 在集成脚本中连接现有 public.users',
      col('user_id', BigInteger, nullable=True), col('staff_code'), col('display_name'),
      enum('status', ['active','inactive'], 'active'),
      unique=[('staff_code',), ('user_id',)])
table('roles', '角色定义；业务权限与资源范围分别管理', col('code'), col('name'), unique=[('code',)])
table('permissions', '权限目录，例如 maintenance:read；代码侧白名单解释',
      col('code'), col('description'), unique=[('code',)])
table('staff_roles', '员工角色关联', ref('staff_id','staff'), ref('role_id','roles'), unique=[('staff_id','role_id')])
table('role_permissions', '角色权限关联', ref('role_id','roles'), ref('permission_id','permissions'), unique=[('role_id','permission_id')])
table('properties', '房源；设施和地理展示信息可扩展，授权不使用 JSON',
      col('reference'), col('address'), col('bedrooms',Integer), col('bathrooms',Integer),
      col('weekly_rent',MONEY), col('currency',default="'AUD'"),
      enum('status',['available','occupied','unavailable'],'available'),
      enum('listing_visibility',['private','public'],'private'), col('attributes',J,default="'{}'::jsonb"),
      unique=[('reference',)], checks=['bedrooms >= 0','bathrooms >= 0','weekly_rent >= 0',"currency ~ '^[A-Z]{3}$'"])
table('staff_property_scopes', '员工可访问房源；权限码仍需单独验证',
      ref('staff_id','staff'), ref('property_id','properties'), col('valid_from',TS,default='CURRENT_TIMESTAMP'),
      col('valid_until',TS,nullable=True), unique=[('staff_id','property_id')],
      checks=['valid_until IS NULL OR valid_until > valid_from'])
table('parties', '业主、租客、供应商主体；联系信息需服务层脱敏',
      enum('kind',['owner','tenant','prospect','vendor']), col('user_id',BigInteger,nullable=True), col('name'), col('contact',J,default="'{}'::jsonb"))
table('property_owners', '房源与业主关联', ref('property_id','properties'), ref('party_id','parties'),
      col('share',Numeric(7,6)), unique=[('property_id','party_id')], checks=['share > 0 AND share <= 1'])
table('leases', '租约；包含金额币种与有效日期', ref('property_id','properties'), col('reference'),
      col('starts_on',Date), col('ends_on',Date), col('weekly_rent',MONEY), col('currency',default="'AUD'"),
      enum('status',['draft','active','expired','terminated'],'draft'), unique=[('reference',)],
      checks=['ends_on >= starts_on','weekly_rent >= 0',"currency ~ '^[A-Z]{3}$'"])
table('lease_tenants', '一份租约的多位租客', ref('lease_id','leases'), ref('party_id','parties'), unique=[('lease_id','party_id')])
table('rent_invoices', '应收租金；逾期由到期日与实收余额计算', ref('lease_id','leases'), col('reference'),
      col('due_on',Date), col('period_start',Date), col('period_end',Date), col('amount',MONEY), col('currency',default="'AUD'"),
      enum('status',['issued','void'],'issued'), unique=[('reference',)], checks=['amount >= 0','period_end >= period_start'])
table('payments', '实收支付；退款扩展为独立冲销流水，当前仅建收款框架',
      col('reference'), col('received_at',TS), col('amount',MONEY), col('currency',default="'AUD'"),
      col('provider_reference',nullable=True), unique=[('reference',),('provider_reference',)], checks=['amount > 0'])
table('payment_allocations', '收款核销到账单；跨行余额和币种由事务服务校验',
      ref('payment_id','payments'), ref('invoice_id','rent_invoices'), col('amount',MONEY),
      unique=[('payment_id','invoice_id')], checks=['amount > 0'])
table('tenancy_applications', '潜在租客申请；双方通过同一服务操作，禁止各自复制业务真相',
      ref('property_id','properties'), ref('applicant_id','parties'), col('reference'),
      enum('status',['draft','submitted','under_review','approved','rejected','withdrawn'],'draft'),
      col('submitted_at',TS,nullable=True), col('version',Integer,default='1'), unique=[('reference',)],
      checks=['version > 0'])
table('viewing_appointments', '看房预约；具体预约冲突规则由事务服务执行',
      ref('property_id','properties'), ref('prospect_id','parties'), ref('host_staff_id','staff',True),
      col('starts_at',TS), col('ends_at',TS), enum('status',['requested','confirmed','completed','cancelled'],'requested'),
      col('idempotency_key'), unique=[('idempotency_key',)], checks=['ends_at > starts_at'])
table('property_favorites', '潜在租客收藏房源；已登录用户映射到本组织主体',
      ref('party_id','parties'), ref('property_id','properties'), unique=[('party_id','property_id')])
table('maintenance_orders', '正式维修工单；不把模拟草稿混入本表',
      ref('property_id','properties'), col('reference'), col('summary'),
      enum('priority',['low','medium','high','urgent'],'medium'),
      enum('status',['open','in_progress','completed','cancelled'],'open'),
      ref('reported_by_party_id','parties',True), ref('assigned_staff_id','staff',True), ref('vendor_id','parties',True), col('version',Integer,default='1'),
      unique=[('reference',)], checks=['version > 0'])
table('maintenance_events', '工单状态变更与处理历史', ref('order_id','maintenance_orders'),
      ref('actor_staff_id','staff'), col('event_type'), col('details',J,default="'{}'::jsonb"))
table('inspections', '人工检查或入住退租检查', ref('property_id','properties'), ref('inspector_id','staff',True),
      enum('kind',['routine','move_in','move_out','video']), col('inspected_at',TS),
      enum('status',['scheduled','completed','cancelled'],'scheduled'), col('summary',default="''"))
table('inspection_findings', '检查发现；证据通过 inspection_reports 关联现有报告与文件',
      ref('inspection_id','inspections'), col('area'), col('description'),
      enum('severity',['info','low','medium','high','critical']), col('evidence',J,default="'[]'::jsonb"))
table('inspection_reports', '检查与现有 public.reports 桥接；不复制报告 JSON 或媒体',
      ref('inspection_id','inspections'), col('report_id',BigInteger), unique=[('inspection_id','report_id')])
table('report_jobs', '现有视频分析图的未来持久化运行；不代表已接入 worker/checkpoint',
      col('requested_by_user_id',BigInteger), col('input_file_id',BigInteger), col('report_id',BigInteger,nullable=True),
      ref('inspection_id','inspections',True), enum('status',['queued','running','completed','failed','cancelled'],'queued'),
      col('validation_passed',Boolean,nullable=True), col('idempotency_key'),
      col('pipeline_version'), col('finished_at',TS,nullable=True), unique=[('requested_by_user_id','idempotency_key')])
table('report_job_steps', '视频抽帧、检测、报告生成等阶段运行指标；不存原始图像字节或隐藏思维链',
      ref('job_id','report_jobs'), col('step_name'), col('attempt',Integer),
      enum('status',['running','completed','failed','skipped']), col('metrics',J,default="'{}'::jsonb"),
      col('error_code',nullable=True), unique=[('job_id','step_name','attempt')], checks=['attempt > 0'])
table('knowledge_bases', '知识库与外部检索服务定位；向量存储可后接',
      col('code'), col('name'), enum('audience',['staff','tenant','public'],'staff'), col('retrieval_provider'), col('external_dataset_id',nullable=True), unique=[('code',)])
table('knowledge_role_access', '知识库访问角色；员工必须在调用检索前通过检查',
      ref('knowledge_base_id','knowledge_bases'), ref('role_id','roles'), unique=[('knowledge_base_id','role_id')])
table('knowledge_documents', '知识文档版本和来源；正文文件复用 public.files',
      ref('knowledge_base_id','knowledge_bases'), col('document_key'), col('version',Integer),
      col('title'), col('file_id',BigInteger,nullable=True), col('external_document_id',nullable=True),
      enum('status',['draft','published','retired'],'draft'),
      unique=[('knowledge_base_id','document_key','version')], checks=['version > 0'])
table('agent_definitions', '版本化 Agent 注册；A2A 只是可选适配器，密钥不入本表',
      col('code'), col('version'), enum('transport',['local','a2a'],'local'),
      col('endpoint',nullable=True), col('credential_ref',nullable=True), col('capabilities',J,default="'[]'::jsonb"),
      col('enabled',Boolean,default='false'), unique=[('code','version')],
      checks=["transport != 'a2a' OR endpoint IS NOT NULL"])
table('prompt_versions', '员工意图拆分提示词的不可变版本；路由策略单独版本化',
      ref('agent_id','agent_definitions'), col('version'), col('content'), col('sha256'),
      unique=[('agent_id','version')])
table('staff_sessions', '员工会话；与当前消费者聊天表分离', ref('staff_id','staff'),
      col('title',default="''"), enum('status',['active','archived'],'active'))
table('staff_requests', '完整原始请求及最终路由；idempotency_key 由调用端传入并绑定员工',
      ref('session_id','staff_sessions'), col('original_text'), col('idempotency_key'),
      enum('route',['pending','execute','human','clarify'],'pending'),
      enum('status',['received','planned','running','completed','partial','failed','needs_input','needs_review'],'received'),
      col('policy_version',default="'staff-v2'"), col('route_reason',nullable=True), col('final_answer',nullable=True),
      col('updated_at',TS,default='CURRENT_TIMESTAMP'), unique=[('session_id','idempotency_key')])
table('intent_runs', '意图模型调用记录；保存模型输出但不把它当成已授权任务',
      ref('request_id','staff_requests'), ref('prompt_id','prompt_versions'), col('model'),
      col('attempt',Integer), enum('status',['ok','invalid','error']), col('raw_output',J,nullable=True),
      col('validation_errors',J,default="'[]'::jsonb"), col('latency_ms',Integer,nullable=True),
      unique=[('request_id','attempt')], checks=['attempt > 0','latency_ms IS NULL OR latency_ms >= 0'])
table('staff_tasks', '只存校验后的任务；无效模型输出留在 intent_runs',
      ref('request_id','staff_requests'), ref('intent_run_id','intent_runs'), col('task_key'), col('ordinal',Integer),
      col('source_text'), col('span_start',Integer), col('span_end',Integer),
      enum('intent',['knowledge_question','record_query','action_request','unclear']),
      col('business_domain'), col('condition_text',default="''"),
      enum('status',['pending','running','ok','denied','unsupported','needs_input','needs_review','failed','skipped'],'pending'),
      col('parameters',J,default="'{}'::jsonb"), unique=[('request_id','task_key'),('request_id','ordinal'),('request_id','id')],
      checks=['ordinal > 0','span_start >= 0','span_end > span_start'])
metadata.tables['staff_agent.intent_runs'].append_constraint(UniqueConstraint('organization_id','request_id','id'))
metadata.tables['staff_agent.staff_tasks'].append_constraint(ForeignKeyConstraint(
    ['organization_id','request_id','intent_run_id'],
    ['staff_agent.intent_runs.organization_id','staff_agent.intent_runs.request_id','staff_agent.intent_runs.id']))
# Dependencies must refer to tasks in the same request, not merely the same organization.
t = table('task_dependencies', '保留任务依赖图；staff-v2 策略不自动执行有依赖的请求',
      ref('request_id','staff_requests'), col('task_id',BigInteger), col('depends_on_id',BigInteger),
      unique=[('task_id','depends_on_id')], checks=['task_id != depends_on_id'])
for key in ('task_id','depends_on_id'):
    t.append_constraint(ForeignKeyConstraint(['organization_id','request_id',key],
        ['staff_agent.staff_tasks.organization_id','staff_agent.staff_tasks.request_id','staff_agent.staff_tasks.id']))
table('task_runs', '执行尝试；worker 租约用于未来恢复，单有表不代表已经实现队列',
      ref('task_id','staff_tasks'), ref('agent_id','agent_definitions',True), col('attempt',Integer),
      enum('status',['running','ok','denied','unsupported','needs_input','failed','cancelled']),
      col('started_at',TS,default='CURRENT_TIMESTAMP'), col('finished_at',TS,nullable=True),
      col('lease_until',TS,nullable=True), col('worker_id',nullable=True), col('error_code',nullable=True),
      unique=[('task_id','attempt')], checks=['attempt > 0','finished_at IS NULL OR finished_at >= started_at'])
table('tool_calls', '工具调用轨迹；输入脱敏，授权由工具服务重验', ref('run_id','task_runs'),
      col('call_key'), col('tool_name'), enum('effect',['read','draft','write']),
      enum('authorization_decision',['allow','deny']), enum('status',['started','ok','failed','denied']),
      col('arguments_redacted',J,default="'{}'::jsonb"), col('result_summary',J,default="'{}'::jsonb"),
      col('duration_ms',Integer,nullable=True), unique=[('run_id','call_key')],
      checks=["authorization_decision != 'deny' OR status = 'denied'",'duration_ms IS NULL OR duration_ms >= 0'])
table('task_results', '每个执行尝试的结构化结果；状态不从自然语言回答反推',
      ref('run_id','task_runs'), col('answer'), col('data',J,default="'{}'::jsonb"),
      enum('source',['mock','business','knowledge']), col('business_persisted',Boolean,default='false'),
      col('approval_submitted',Boolean,default='false'), unique=[('run_id',)],
      checks=["source != 'mock' OR (NOT business_persisted AND NOT approval_submitted)"])
table('maintenance_drafts', '维修草稿内容；可持久化模拟内容但不得宣称写入业务系统',
      ref('task_id','staff_tasks'), ref('property_id','properties'), ref('created_by','staff'),
      col('summary'), enum('priority',['low','medium','high','urgent'],'medium'),
      enum('mode',['mock','live'],'mock'), enum('status',['simulated','draft','submitted','discarded'],'simulated'),
      col('idempotency_key'), unique=[('idempotency_key',)], checks=["mode != 'mock' OR status IN ('simulated','discarded')"])
table('human_cases', '人工案件；需要人工与已成功外部提交分开表示',
      ref('request_id','staff_requests'), ref('assigned_staff_id','staff',True), col('reason'),
      enum('status',['needs_review','queued','in_progress','resolved','cancelled'],'needs_review'),
      enum('submission_status',['not_submitted','pending','submitted','failed'],'not_submitted'),
      col('external_reference',nullable=True), col('submitted_at',TS,nullable=True),
      unique=[('request_id',)], checks=["submission_status != 'submitted' OR (external_reference IS NOT NULL AND submitted_at IS NOT NULL)"])
table('approval_requests', '未来真实操作审批；审批通过不等于执行成功',
      ref('draft_id','maintenance_drafts'), ref('requested_by','staff'), ref('reviewer_id','staff',True),
      enum('status',['pending','approved','rejected','cancelled'],'pending'), col('decision_at',TS,nullable=True),
      col('decision_note',nullable=True), checks=["status NOT IN ('approved','rejected') OR (reviewer_id IS NOT NULL AND decision_at IS NOT NULL)"])
table('a2a_delegations', '未来远端任务映射；暂不启动网络通信',
      ref('run_id','task_runs'), ref('agent_id','agent_definitions'), col('remote_task_id',nullable=True),
      col('remote_context_id',nullable=True), col('protocol_version'), col('idempotency_key'),
      enum('status',['pending','working','input_required','completed','failed','cancelled','unknown'],'pending'),
      col('last_event_id',nullable=True), col('artifacts',J,default="'[]'::jsonb"),
      unique=[('agent_id','remote_task_id'),('idempotency_key',)])
table('outbox_events', '事务内写入待发送事件；dispatcher 未来实现，交付按至少一次设计',
      col('event_key'), col('event_type'), col('aggregate_type'), col('aggregate_id',BigInteger),
      col('payload',J), enum('status',['pending','delivered','failed'],'pending'),
      col('attempts',Integer,default='0'), col('available_at',TS,default='CURRENT_TIMESTAMP'),
      col('delivered_at',TS,nullable=True), unique=[('event_key',)], checks=['attempts >= 0'])
table('audit_events', '审计元数据；生产服务角色应仅允许 INSERT/SELECT',
      ref('actor_staff_id','staff',True), ref('request_id','staff_requests',True), col('event_type'),
      col('resource_type'), col('resource_id',nullable=True), col('details_redacted',J,default="'{}'::jsonb"))

for name, keys in {
    'staff_requests':['session_id','created_at'], 'staff_tasks':['request_id','ordinal'],
    'maintenance_orders':['property_id','status'], 'rent_invoices':['lease_id','due_on'],
    'inspections':['property_id','inspected_at'], 'audit_events':['request_id','created_at'],
    'outbox_events':['status','available_at'], 'human_cases':['status','created_at'],
}.items():
    t = metadata.tables[OWNERS[name]+'.'+name]
    Index('ix_'+name+'_lookup',t.c.organization_id,*(t.c[k] for k in keys))
t = metadata.tables['staff_agent.task_runs']
Index('uq_task_runs_one_active',t.c.organization_id,t.c.task_id,unique=True,
      postgresql_where=text("status = 'running'"))


def export():
    root = Path(__file__).parent
    (root/'services').mkdir(exist_ok=True)
    dictionary = ['# 数据字典（生成文件）', '',
                  '按服务 schema 划分；生产可独立数据库。仅服务内建立外键；跨服务 ID 为逻辑引用。',
                  '所有新增表除 organizations 外均有 organization_id。删除默认 NO ACTION。', '']
    all_sql = ['-- GENERATED. Isolated simulation only. No existing public tables modified.', 'BEGIN;']
    for service in SERVICE_TABLES:
        service_sql = [f'CREATE SCHEMA {service};']
        for t in metadata.sorted_tables:
            if t.schema != service: continue
            service_sql.append(str(CreateTable(t).compile(dialect=dialect()))+';')
            service_sql += [str(CreateIndex(i).compile(dialect=dialect()))+';' for i in sorted(t.indexes,key=lambda i:i.name)]
            dictionary += [f'## {t.fullname}', '', t.comment or '', '', '| 字段 | 类型 | 可空 | 默认值 | 说明 |', '|---|---|---|---|---|']
            for c in t.c:
                dictionary.append(f'| {c.name} | {c.type.compile(dialect=dialect())} | {"是" if c.nullable else "否"} | {c.server_default.arg if c.server_default is not None and hasattr(c.server_default,"arg") else ""} | {c.comment or ""} |')
            dictionary += ['', '约束与关联：', '']
            for con in t.constraints:
                if isinstance(con,ForeignKeyConstraint):
                    dictionary.append('- FK '+', '.join(con.column_keys)+' → '+', '.join(e.target_fullname for e in con.elements))
                elif isinstance(con,UniqueConstraint): dictionary.append('- UNIQUE '+', '.join(c.name for c in con.columns))
                elif isinstance(con,CheckConstraint): dictionary.append('- CHECK `'+str(con.sqltext)+'`')
            for src,colname,target in LOGICAL_LINKS:
                if src == t.name: dictionary.append(f'- 跨服务逻辑引用 {colname} → {OWNERS[target]}.{target}.id；由 API / 事件校验，非数据库外键')
            dictionary += ['']
        (root/'services'/f'{service}.sql').write_text('BEGIN;\n'+'\n\n'.join(service_sql)+'\nCOMMIT;\n')
        all_sql += service_sql
    all_sql.append('COMMIT;')
    (root/'001_schema.sql').write_text('\n\n'.join(all_sql)+'\n')
    (root/'DATA_DICTIONARY.md').write_text('\n'.join(dictionary)+'\n')
    print(f'Exported {len(metadata.tables)} tables across {len(SERVICE_TABLES)} services')

if __name__ == '__main__': export()
