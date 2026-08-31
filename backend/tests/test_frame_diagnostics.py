import asyncio
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.api import report as api
from app.auth import require_user
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
        with patch.dict(app.dependency_overrides, {require_user: lambda: {'user_id':1}}), \
             patch.object(api, 'resolve_chat_internal_id', return_value=1), \
             patch.object(api, 'get_chat', return_value={'user_id':1}), \
             patch.object(api, 'chat_has_report', return_value=False), \
             patch.object(api, '_resolve_user_video_asset', return_value='test-video'), \
             patch.object(WorkflowOrchestrator, 'execute_workflow', return_value=state):
            response = TestClient(app).post('/api/processVideoStream', json={
                'chat_id':'test-chat', 'video_asset_id':'test-video'})
        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertEqual([e['type'] for e in events], ['error', 'end'])
        self.assertEqual(events[0]['frameStats']['extracted'], 25)
        self.assertEqual(events[0]['message'], state['warning'])
        self.assertNotIn(1, api._processing_chats)


if __name__ == '__main__':
    unittest.main()
