import test from 'node:test';
import assert from 'node:assert/strict';
import { hasReportContent, hasReportHistoryContent } from '../src/utils/reportState.js';

test('failed or empty history must not lock report retries', () => {
  for (const report of [null, {}, {error:'model unavailable'}, {regions:[]},
    {regions:'invalid'}, {regions:[{}], error:'failure'}]) {
    assert.equal(hasReportContent(report), false);
  }
});

test('real report content still locks duplicate generation', () => {
  assert.equal(hasReportContent({regions:[{regionName:['Kitchen']}]}), true);
});

test('PDF history remains supported independently of analysis content', () => {
  const pdf = {source_type:'pdf', title:'Uploaded document'};
  assert.equal(hasReportHistoryContent(pdf), true);
  assert.equal(hasReportContent(pdf), false);
  assert.equal(hasReportHistoryContent({error:'failure'}), false);
});
