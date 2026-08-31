import json
import os
import asyncio
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import httpx
from openai import NotFoundError, BadRequestError
from fastapi.testclient import TestClient
from app.agents.report_writer_agent import ReportWriterAgent
from app.report_errors import ReportGenerationError
from app.workflow.graph import ReportServices
from app.workflow.orchestrator import WorkflowOrchestrator
from app.persistence import repositories
from app.persistence.database import get_connection
from app.api import report as api
from app.auth import require_user
from main import create_app
from app.llm import complete


class ModelFailureTests(unittest.TestCase):
    def test_billing_error_is_translated_without_provider_body(self):
        response = httpx.Response(400, request=httpx.Request('POST', 'https://provider.invalid'))
        error = BadRequestError('private-billing-body', response=response,
                                body={'error':{'code':'Arrearage','message':'private-billing-body'}})
        client = MagicMock()
        client.chat.completions.create = AsyncMock(side_effect=error)
        with self.assertRaises(ReportGenerationError) as caught:
            asyncio.run(complete([], 'L3', client=client))
        self.assertIn('Arrearage', str(caught.exception))
        self.assertNotIn('private-billing-body', str(caught.exception))
        client.chat.completions.create.assert_awaited_once()

    def test_role_does_not_retry_provider_billing_failure(self):
        with patch('app.workflow.graph.complete', new_callable=AsyncMock,
                   side_effect=ReportGenerationError('Arrearage')) as call:
            with self.assertRaises(ReportGenerationError):
                asyncio.run(ReportServices()._json('system', 'user'))
            call.assert_awaited_once()

    def test_provider_failure_is_safe_exception_not_report(self):
        response = httpx.Response(404, request=httpx.Request('POST', 'https://provider.invalid'))
        error = NotFoundError('private-provider-body', response=response, body={'error':'private-provider-body'})
        with patch.object(ReportWriterAgent, '_call_llm', side_effect=error), \
             self.assertLogs('app.agents.report_writer_agent', level='ERROR') as logs:
            with self.assertRaises(ReportGenerationError) as caught:
                ReportWriterAgent().write_report([], [], {}, {}, {}, {}, {})
        self.assertIn('HTTP 404', str(caught.exception))
        self.assertNotIn('private-provider-body', str(caught.exception) + '\n'.join(logs.output))

    def test_invalid_report_blocked_before_database_writes(self):
        for report in ({}, {'error':'failure'}, {'regions':[]}, {'regions':'invalid'}):
            with self.subTest(report=report), patch.object(repositories, '_get_connection') as connect:
                with self.assertRaises(ReportGenerationError):
                    repositories.store_report([], 'unused', report)
                connect.assert_not_called()
            with patch('app.workflow.graph.db.store_report') as save:
                with self.assertRaises(ReportGenerationError):
                    ReportServices().persist({'draft_report':report})
                save.assert_not_called()

    def test_failed_model_or_error_state_emits_error_not_complete(self):
        state = {'run_id':'test', 'video_asset_id':'test', 'draft_report':{'error':'private-failure'}, 'report_id':1}
        for outcome in (ReportGenerationError('Model unavailable. No report saved.'), state):
            app = create_app()
            kwargs = {'side_effect':outcome} if isinstance(outcome, Exception) else {'return_value':outcome}
            with patch.dict(app.dependency_overrides, {require_user:lambda:{'user_id':1}}), \
                 patch.object(api, 'resolve_chat_internal_id', return_value=1), \
                 patch.object(api, 'get_chat', return_value={'user_id':1}), \
                 patch.object(api, 'chat_has_report', return_value=False), \
                 patch.object(api, '_resolve_user_video_asset', return_value='test'), \
                 patch.object(WorkflowOrchestrator, 'execute_workflow', **kwargs):
                response = TestClient(app).post('/api/processVideoStream', json={'chat_id':'test','video_asset_id':'test'})
            events = [json.loads(line) for line in response.text.splitlines()]
            self.assertEqual([e['type'] for e in events], ['error', 'end'])
            self.assertEqual(events[0]['code'], 'report_generation_failed')
            self.assertNotIn('private-failure', response.text)
            self.assertNotIn(1, api._processing_chats)

    def test_retry_query_against_postgres_without_writes(self):
        if os.environ.get('RUN_DB_CHECK') != '1':
            self.skipTest('Set RUN_DB_CHECK=1 inside the backend container for read-only PostgreSQL checks')
        connection = MagicMock()
        with patch.object(repositories, '_get_connection', return_value=connection):
            repositories.chat_has_report(42)
        cursor = connection.cursor.return_value.__enter__.return_value
        query, params = cursor.execute.call_args.args
        prefix = ("WITH reports(id,origin_chat_id,report_kind,status) AS (VALUES(1,42,'analysis',%s)), "
                  "report_analysis(report_id,report_json) AS (VALUES(1,CAST(%s AS jsonb))) ")
        for report, status, expected in (
            ({'error':'old failure'}, 'active', False), ({}, 'active', False),
            ({'regions':[]}, 'active', False), ({'regions':'invalid'}, 'active', False),
            ({'regions':[{}]}, 'active', True), ({'regions':[{}]}, 'deleted', False),
            ({'regions':[{}], 'error':'failure'}, 'active', False)):
            with self.subTest(report=report, status=status), get_connection() as conn, conn.cursor() as cur:
                cur.execute(prefix + query, (status, json.dumps(report), *params))
                self.assertEqual(cur.fetchone() is not None, expected)


if __name__ == '__main__':
    unittest.main()
