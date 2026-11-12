/** Stable across reconnects and historical replay; never reuse the chat request ID. */
export function runtimeMonitorNoticeId(payload: Record<string, unknown>): string | null {
  if (payload.notice_type !== 'runtime_intervention') return null;
  const noticeId = payload.notice_id;
  if (typeof noticeId !== 'string' || !noticeId.trim()) return null;
  return `runtime-monitor-notice-${noticeId}`;
}
