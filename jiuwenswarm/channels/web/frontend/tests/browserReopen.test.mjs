import assert from 'node:assert/strict';
import { after, afterEach, beforeEach, test } from 'node:test';
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost/' });
for (const [key, value] of Object.entries({
  window: dom.window, document: dom.window.document, navigator: dom.window.navigator,
  localStorage: dom.window.localStorage, CustomEvent: dom.window.CustomEvent,
  MutationObserver: dom.window.MutationObserver, Element: dom.window.Element,
  ResizeObserver: class { observe() {} disconnect() {} },
  IS_REACT_ACT_ENVIRONMENT: true,
})) {
  Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
}
after(() => dom.window.close());
window.requestAnimationFrame = callback => { callback(0); return 0; };
window.cancelAnimationFrame = () => {};

const { act, createElement } = await import('react');
const { createRoot } = await import('react-dom/client');
const {
  useChatStore, applyBrowserDisplaySettings, closeDesktopBrowserTab,
  useDesktopBrowserAutoOpen, useDesktopBrowserTabFlags, DesktopBrowserPane,
} = await import('../node_modules/.cache/browser-reopen/exports.mjs');

let panels;
let listeners;
let opened;
let root;
let container;
let sessionId;
let flags;

function panel(owner = 'one', id = owner, busy = true) {
  return { sessionId: owner, panelId: id, memberId: '', busy, url: 'https://example.test/' };
}

function Probe() {
  useDesktopBrowserAutoOpen(sessionId, () => opened.push(sessionId));
  flags = useDesktopBrowserTabFlags(sessionId);
  return createElement('output', null, JSON.stringify(flags));
}

async function mount(owner = 'one') {
  sessionId = owner;
  useChatStore.setState({ activeSessionId: owner });
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(createElement(Probe)));
}

async function selectSession(owner) {
  sessionId = owner;
  useChatStore.setState({ activeSessionId: owner });
  await act(async () => root.render(createElement(Probe)));
}

async function emit(next) {
  panels = next;
  await act(async () => listeners.forEach(listener => listener(next)));
}

async function closeTab() {
  await act(async () => closeDesktopBrowserTab());
  assert.equal(flags.closed, true);
}

beforeEach(async () => {
  panels = [];
  listeners = new Set();
  opened = [];
  localStorage.clear();
  window.jiuwenDesktop = {
    isElectron: true,
    browser: {
      listPanels: async owner => panels.filter(item => item.sessionId === owner),
      onPanelsChanged: listener => { listeners.add(listener); return () => listeners.delete(listener); },
      setHeadless: async value => value,
      // No navigation, restart or MCP operations are available to the hook.
    },
  };
  await applyBrowserDisplaySettings({ headless: false });
});

afterEach(async () => {
  if (root) await act(async () => root.unmount());
  root = null;
  container?.remove();
  assert.equal(listeners.size, 0);
});

test('a new task reopens a closed tab, but navigation and repeated notifications do not', async () => {
  await mount();
  await emit([panel()]);
  assert.deepEqual(opened, ['one']);
  assert.deepEqual(flags, { requested: true, closed: false });
  await closeTab();
  await emit([{ ...panel(), url: 'https://example.test/next', title: 'Next' }]);
  await emit([panel(), panel('two')]);
  assert.equal(flags.closed, true);
  assert.deepEqual(opened, ['one']);
  await emit([panel('one', 'one', false), panel('two')]);
  await emit([panel(), panel('two')]);
  assert.deepEqual(opened, ['one', 'one']);
  assert.equal(flags.closed, false);
});

test('legacy persisted close flags are cleared only by a new task', async () => {
  localStorage.setItem('jiuwenclaw_desktop_browser_tab_flags:one', '{"requested":true,"closed":true}');
  panels = [panel('one', 'one', false)];
  await mount();
  assert.equal(flags.closed, true);
  assert.deepEqual(opened, []);
  await emit([panel()]);
  assert.equal(flags.closed, false);
  assert.deepEqual(opened, ['one']);
});

test('restoring existing busy panels does not reopen a manually closed tab', async () => {
  panels = [panel()];
  await mount();
  await closeTab();
  await emit([panel()]);
  assert.deepEqual(opened, []);
  assert.equal(flags.closed, true);
  await emit([]);
  await emit([panel()]);
  assert.deepEqual(opened, ['one']);
});

test('headless tasks stay hidden and an active task can reveal after switching to headed', async () => {
  await applyBrowserDisplaySettings({ headless: true });
  await mount();
  await closeTab();
  await emit([panel()]);
  assert.deepEqual(opened, []);
  assert.equal(flags.closed, true);
  await act(async () => applyBrowserDisplaySettings({ headless: false }));
  assert.deepEqual(opened, ['one']);
  assert.equal(flags.closed, false);
});

test('a headless task that already finished does not open later', async () => {
  await applyBrowserDisplaySettings({ headless: true });
  await mount();
  await closeTab();
  await emit([panel()]);
  await emit([]);
  await act(async () => applyBrowserDisplaySettings({ headless: false }));
  assert.deepEqual(opened, []);
  assert.equal(flags.closed, true);
});

test('background sessions do not steal the active panel; selecting their active task reveals it', async () => {
  await mount();
  await closeTab();
  await emit([panel('two')]);
  assert.deepEqual(opened, []);
  assert.equal(flags.closed, true);
  await selectSession('two');
  assert.deepEqual(opened, ['two']);
  assert.equal(flags.closed, false);
  await selectSession('one');
  assert.equal(flags.closed, true);
  assert.deepEqual(opened, ['two']);
});

test('completed background tasks do not force a panel open when selected later', async () => {
  await mount();
  await emit([panel('two')]);
  await emit([]);
  await selectSession('two');
  assert.deepEqual(opened, []);
  assert.equal(flags.requested, false);
});

test('concurrent member starts reveal once per update, without depending on subagent history', async () => {
  await mount();
  await emit([panel('one', 'alice'), panel('one', 'bob')]);
  assert.deepEqual(opened, ['one']);
  await closeTab();
  await emit([panel('one', 'alice'), panel('one', 'bob')]);
  assert.equal(flags.closed, true);
  await emit([panel('one', 'alice'), panel('one', 'bob'), panel('one', 'carol')]);
  assert.equal(flags.closed, false);
  assert.deepEqual(opened, ['one', 'one']);
});

test('an older list response cannot erase an already received busy transition', async () => {
  let resolve;
  window.jiuwenDesktop.browser.listPanels = () => new Promise(done => { resolve = done; });
  await mount();
  await emit([panel()]);
  await closeTab();
  await act(async () => resolve([]));
  await emit([panel()]);
  assert.deepEqual(opened, ['one']);
  assert.equal(flags.closed, true);
});

test('a failed baseline read still permits later task events', async () => {
  window.jiuwenDesktop.browser.listPanels = async () => { throw new Error('IPC read unavailable'); };
  await mount();
  await emit([panel()]);
  assert.deepEqual(opened, ['one']);
});

test('the hook does not change ordinary web clients', async () => {
  window.jiuwenDesktop = undefined;
  await mount();
  assert.equal(listeners.size, 0);
  assert.deepEqual(opened, []);
});

async function mountPane() {
  const visibleCalls = [];
  Object.assign(window.jiuwenDesktop.browser, {
    setVisible: async (visible, id) => { visibleCalls.push({ visible, id }); },
    setBounds: async () => {},
    getState: async id => panels.find(item => item.panelId === id) ?? panel('one', id, false),
    onStateChanged: () => () => {},
    hideDownloadBubble: async () => {},
    onDownloadBubbleChanged: () => () => {},
  });
  window.jiuwenDesktop.onLayoutInvalidated = () => () => {};
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(createElement(DesktopBrowserPane, { sessionId: 'one' })));
  return visibleCalls;
}

test('pane waits for existing targets and opens a busy member without creating a default page', async () => {
  let resolve;
  window.jiuwenDesktop.browser.listPanels = () => new Promise(done => { resolve = done; });
  const calls = await mountPane();
  assert.deepEqual(calls, []);
  panels = [panel('one', 'one', false), { ...panel('one', 'alice'), memberId: 'alice' }];
  await act(async () => resolve(panels));
  assert.ok(calls.some(item => item.visible && item.id === 'alice'));
  assert.ok(calls.every(item => item.id === 'alice'));
  assert.equal(container.querySelector('[aria-selected="true"]').getAttribute('data-variant'), 'alice');
});

test('pane preserves the user-selected member while task notifications arrive', async () => {
  panels = [panel('one', 'alice'), panel('one', 'bob')];
  await mountPane();
  await act(async () => container.querySelector('[data-variant="bob"]').click());
  await emit([...panels, panel('one', 'carol')]);
  assert.equal(container.querySelector('[aria-selected="true"]').getAttribute('data-variant'), 'bob');
});

test('pane ignores a stale baseline after receiving the actual task panel', async () => {
  let resolve;
  window.jiuwenDesktop.browser.listPanels = () => new Promise(done => { resolve = done; });
  const calls = await mountPane();
  await emit([panel('one', 'alice')]);
  await act(async () => resolve([]));
  assert.ok(calls.every(item => item.id === 'alice'));
});

test('pane still creates the session page for explicit manual open with no existing targets', async () => {
  const calls = await mountPane();
  assert.ok(calls.some(item => item.visible && item.id === 'one'));
});
