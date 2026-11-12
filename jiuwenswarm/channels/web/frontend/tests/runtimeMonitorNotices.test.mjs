import assert from 'node:assert/strict';
import test from 'node:test';
import { runtimeMonitorNoticeId } from '../node_modules/.cache/runtime-monitor/features/runtimeMonitorNotices.mjs';
import { parseHistoryJsonFileToPreviewMessages } from '../node_modules/.cache/runtime-monitor/features/historyRestore.mjs';

function notice(id, content, timestamp, extra = {}) {
  return {
    role: 'assistant', event_type: 'chat.notice', notice_type: 'runtime_intervention',
    notice_id: id, content, timestamp, request_id: 'same-request', ...extra,
  };
}

test('one advice has the same live identity across requests and lifecycle changes', () => {
  const created = notice('task:a', 'Verify', 1);
  const improved = notice('task:a', 'Improved', 2, { request_id: 'resume-request' });
  assert.equal(runtimeMonitorNoticeId(created), runtimeMonitorNoticeId(improved));
  assert.notEqual(runtimeMonitorNoticeId(created), runtimeMonitorNoticeId(notice('task:b', 'Replan', 3)));
  assert.equal(runtimeMonitorNoticeId({ notice_type: 'image_tool_fallback' }), null);
  assert.equal(runtimeMonitorNoticeId({ notice_type: 'runtime_intervention' }), null);
});

test('history restores latest outcome once without dropping ordinary assistant content', () => {
  const messages = parseHistoryJsonFileToPreviewMessages([
    { role: 'user', id: 'user', content: 'Investigate', timestamp: 1 },
    notice('task:a', 'Verify evidence', 2),
    { role: 'assistant', event_type: 'chat.final', id: 'answer', content: 'Done', timestamp: 3 },
    notice('task:a', 'Observed improvement', 4),
    notice('task:a', 'Observed improvement', 4),
  ], 'session-a');
  assert.equal(messages.filter((m) => m.id === 'runtime-monitor-notice-task:a').length, 1);
  assert.equal(messages.find((m) => m.id === 'runtime-monitor-notice-task:a').content, 'Observed improvement');
  assert.equal(messages.find((m) => m.id === 'answer').content, 'Done');
  assert.equal(messages.find((m) => m.id === 'user').content, 'Investigate');
});

test('nested persisted event payload retains stable identity; snapshots are not assistant messages', () => {
  const messages = parseHistoryJsonFileToPreviewMessages([
    { role: 'assistant', event_type: 'chat.notice', timestamp: 1, event_payload: notice('task:a', 'Observe only', 1) },
    { role: 'assistant', event_type: 'chat.runtime_monitor', timestamp: 2, content: 'diagnostics' },
    notice('task:b', 'Verify again', 3),
    { role: 'assistant', event_type: 'chat.notice', timestamp: 4, content: 'unrelated notice' },
  ], 'session-a');
  assert.deepEqual(messages.map((m) => m.id), ['runtime-monitor-notice-task:a', 'runtime-monitor-notice-task:b']);
  assert.ok(messages.every((m) => m.role === 'system'));
});


test('transport dedup preserves advice lifecycle updates within one request', async () => {
  const { makeEventDedupKey } = await import('../node_modules/.cache/runtime-monitor/utils/wsEventDedup.mjs');
  const created = notice('task:a', 'Verify evidence', 1, { session_id: 's1' });
  const improved = notice('task:a', 'Observed improvement', 2, { session_id: 's1' });
  const key = (payload) => makeEventDedupKey('chat.notice', payload);
  assert.notEqual(key(created), key(improved));
  assert.equal(key(improved), key({ ...improved, request_id: 'resumed-request' }));
  assert.notEqual(key(created), key({ ...created, notice_id: 'task:b' }));
  assert.notEqual(key(created), key({ ...created, session_id: 's2' }));
  assert.notEqual(key(created), key({ ...created, runtime_monitor: { advice: { followed: 'YES' } } }));
});
