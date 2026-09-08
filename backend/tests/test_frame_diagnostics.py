import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.api import report as api
from app.auth import require_user
from app.workers import report_worker
from app.workflow.graph import ReportServices, build_report_graph
from app.workflow.orchestrator import WorkflowOrchestrator, result_payload
from main import create_app


class FrameDiagnosticsTests(unittest.TestCase):
    def test_empty_filter_logs_counts_and_stops_before_models(self):
        class Services(ReportServices):
            def authorize(self, state): return {}
            async def extract(self, state):
                return {'frames':['one', 'two'], 'extracted_frame_count':2}
            async def filter(self, state):
                return {'frames':[], 'filter_stats':{'similar':0, 'blurry':2, 'dark':0, 'sensitive':0}}
            async def select(self, state):
                raise AssertionError('Empty frames must not reach a model')
        events = []
        with self.assertLogs('app.workflow.graph', level='INFO') as logs:
            state = asyncio.run(build_report_graph(Services(), events.append).ainvoke(
                {'run_id':'test-run', 'video_asset_id':'test-video'}))
        details = next(e['details'] for e in events if e['step'] == 'filter_complete')
        self.assertEqual((details['input_count'], details['output_count']), (2, 0))
        self.assertEqual(details['rejected']['blurry'], 2)
        self.assertIn('blurry=2', state['warning'])
        self.assertIn('Video stage filter', '\n'.join(logs.output))
        self.assertEqual(result_payload(state)['frameStats']['extracted'], 2)

    def test_empty_result_stream_is_error_not_success(self):
        app = create_app()
        state = {'run_id':'test-run', 'video_asset_id':'test-video', 'extracted_frame_count':25,
                 'frames':[], 'filter_stats':{'blurry':25}, 'warning':'No usable frames remain.'}
        frame_stats = result_payload(state)['frameStats']
        settings = SimpleNamespace(REPORT_PIPELINE_VERSION='test-v1', REPORT_WORKER_INLINE=False,
                                   REPORT_JOB_EVENT_POLL_SECONDS=0.001)
        stored_event = {'sequence_no':1, 'event_type':'error', 'message':state['warning'],
                        'payload':{'code':'workflow_incomplete', 'frameStats':frame_stats}}
        with patch.dict(app.dependency_overrides, {require_user: lambda: {'user_id':1}}), \
             patch.object(api, 'resolve_chat_internal_id', return_value=1), \
             patch.object(api, 'get_chat', return_value={'user_id':1}), \
             patch.object(api, 'chat_has_report', return_value=False), \
             patch.object(api, '_resolve_user_video_asset', return_value='test-video'), \
             patch.object(api, 'get_settings', return_value=settings), \
             patch.object(api, 'create_report_job', return_value={'id':7, 'job_id':'job-7', 'status':'queued'}), \
             patch.object(api, 'get_report_job_events', return_value=[stored_event]), \
             patch.object(api, 'get_report_job', return_value={'status':'failed'}):
            response = TestClient(app).post('/api/processVideoStream', json={
                'chat_id':'test-chat', 'video_asset_id':'test-video'})
        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertEqual([e['type'] for e in events], ['job', 'error', 'end'])
        self.assertEqual(events[1]['frameStats']['extracted'], 25)
        self.assertEqual(events[1]['message'], state['warning'])

    def test_report_job_status_serializes_persisted_state(self):
        app = create_app()
        job = {'id':9, 'job_id':'job-9', 'user_id':1, 'status':'running'}
        with patch.dict(app.dependency_overrides, {require_user: lambda: {'user_id':1}}), \
             patch.object(api, 'get_report_job', return_value=job), \
             patch.object(api, 'get_report_job_events', return_value=[]), \
             patch.object(api, 'get_report_job_steps', return_value=[]):
            response = TestClient(app).get('/api/report-jobs/job-9')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['job']['status'], 'running')

    def test_incomplete_worker_persists_frame_diagnostics(self):
        state = {'run_id':'test-run', 'video_asset_id':'test-video', 'extracted_frame_count':25,
                 'frames':[], 'filter_stats':{'blurry':25}, 'warning':'No usable frames remain.'}
        job = {'id':10, 'job_id':'job-10', 'user_id':1, 'workspace_id':2,
               'video_asset_id':'test-video', 'input_payload':{}, 'attempt':1}
        with patch.object(report_worker, '_recovered_result', return_value=None), \
             patch.object(report_worker, 'get_settings', return_value=SimpleNamespace(REPORT_JOB_LEASE_SECONDS=60)), \
             patch.object(WorkflowOrchestrator, 'execute_workflow', return_value=state), \
             patch.object(report_worker.db, 'fail_report_job', return_value='failed') as fail:
            self.assertEqual(report_worker.execute_claimed_job(job, 'test-worker'), 'failed')
        self.assertEqual(fail.call_args.kwargs['payload']['frameStats']['extracted'], 25)


if __name__ == '__main__':
    unittest.main()
