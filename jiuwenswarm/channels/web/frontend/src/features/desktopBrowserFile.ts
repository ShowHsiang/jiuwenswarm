import { useCallback, useEffect, useRef, useState } from 'react';
import { getApiBase } from '../utils/env';
import { useChatStore } from '../stores/chatStore';
import { useSessionStore } from '../stores/sessionStore';
import { openSingleAgentPanel } from './singleAgentPanelState';
import { openTeamPanel } from './teamPanelState';
import { isDesktopBrowserHeadless, useDesktopBrowserHeadless } from './desktopBrowserDisplay';

const DESKTOP_BROWSER_TAB_EVENT = 'jiuwenclaw-desktop-browser-tab-change';
const DESKTOP_BROWSER_TAB_FLAGS_KEY = 'jiuwenclaw_desktop_browser_tab_flags';

const DESKTOP_BROWSER_FILE_EXTENSIONS = new Set(['html', 'htm', 'md', 'markdown']);

/** browser 页签的出现/关闭标志，按会话隔离避免跨会话互相污染。 */
interface DesktopBrowserTabFlags {
  /** A file preview or live browser task requested this session's pane. */
  requested: boolean;
  /** 用户点关闭按钮显式关掉了 browser 页签 */
  closed: boolean;
}

const EMPTY_TAB_FLAGS: DesktopBrowserTabFlags = { requested: false, closed: false };

function tabFlagsStorageKey(sessionId: string): string {
  return `${DESKTOP_BROWSER_TAB_FLAGS_KEY}:${sessionId || 'default'}`;
}

function loadDesktopBrowserTabFlags(sessionId: string): DesktopBrowserTabFlags {
  try {
    const raw = window.localStorage.getItem(tabFlagsStorageKey(sessionId));
    if (!raw) return { ...EMPTY_TAB_FLAGS };
    const parsed = JSON.parse(raw) as Partial<DesktopBrowserTabFlags> | null;
    return {
      requested: parsed?.requested === true,
      closed: parsed?.closed === true,
    };
  } catch {
    return { ...EMPTY_TAB_FLAGS };
  }
}

function persistDesktopBrowserTabFlags(sessionId: string, patch: Partial<DesktopBrowserTabFlags>): void {
  const next = { ...loadDesktopBrowserTabFlags(sessionId), ...patch };
  try {
    window.localStorage.setItem(tabFlagsStorageKey(sessionId), JSON.stringify(next));
  } catch {
    // localStorage 不可用时仅当前内存态生效，不影响本次点击。
  }
  window.dispatchEvent(new CustomEvent(DESKTOP_BROWSER_TAB_EVENT));
}

function activeSessionId(): string {
  return useChatStore.getState().activeSessionId ?? '';
}

/**
 * 下载链接带上 inline=1：后端以 Content-Disposition: inline 返回，
 * BrowserView 才会直接渲染 html/md 而不是触发保存。
 */
function buildInlineFileUrl(downloadUrl: string | null | undefined): string | null {
  const trimmed = downloadUrl?.trim();
  if (!trimmed) return null;
  try {
    const url = new URL(trimmed, getApiBase() || window.location.href);
    url.searchParams.set('inline', '1');
    return url.toString();
  } catch {
    return null;
  }
}

function openDesktopBrowserPanel(): void {
  const mode = useSessionStore.getState().runtimes[activeSessionId()]?.mode ?? 'agent';
  if (mode === 'team' || mode === 'auto_harness') {
    openTeamPanel('browser');
    return;
  }
  openSingleAgentPanel('browser');
}

/** 桌面内置浏览器可打开文件的最小结构（FileDownloadItem / ArtifactItem 均满足）。 */
export interface DesktopBrowserOpenableFile {
  name: string;
  download_url?: string | null;
}

/**
 * Electron 内置浏览器打开聊天文件（.html/.md）。
 * 命中时导航 BrowserView 并切到 browser 页签，返回 true；非 Electron、
 * 不可预览或缺少下载链接时返回 false，调用方继续走产物面板预览。
 */
export function openFileInDesktopBrowser(file: DesktopBrowserOpenableFile): boolean {
  if (!window.jiuwenDesktop) return false;
  if (isDesktopBrowserHeadless()) return false;
  if (!isDesktopBrowserPreviewableFile(file.name)) return false;
  const url = buildInlineFileUrl(file.download_url);
  if (!url) return false;
  const sessionId = activeSessionId();
  persistDesktopBrowserTabFlags(sessionId, { requested: true, closed: false });
  void window.jiuwenDesktop.browser.navigate(url, sessionId).catch((error) => {
    console.warn('[desktop.browser] file open failed:', error);
  });
  openDesktopBrowserPanel();
  return true;
}

/** 关闭 browser 页签：页签隐藏、DesktopBrowserPane 卸载时自动隐藏 BrowserView。 */
export function closeDesktopBrowserTab(): void {
  persistDesktopBrowserTabFlags(activeSessionId(), { closed: true });
}

/** Reopen on a new MCP task binding, not on retained subagent history or navigation. */
export function useDesktopBrowserAutoOpen(sessionId: string, onOpen: () => void): void {
  const desktop = window.jiuwenDesktop;
  const headless = useDesktopBrowserHeadless();
  const current = useRef({ sessionId, onOpen });
  current.current = { sessionId, onOpen };
  const busyPanels = useRef(new Map<string, string>());
  const pendingSessions = useRef(new Set<string>());
  const eventRevision = useRef(0);

  const revealPending = useCallback(() => {
    const currentSession = current.current.sessionId;
    if (isDesktopBrowserHeadless() || !pendingSessions.current.has(currentSession)) return;
    pendingSessions.current.delete(currentSession);
    persistDesktopBrowserTabFlags(currentSession, { requested: true, closed: false });
    current.current.onOpen();
  }, []);

  useEffect(() => {
    if (!desktop?.isElectron) return;
    return desktop.browser.onPanelsChanged((panels) => {
      eventRevision.current += 1;
      const nextBusy = new Map<string, string>();
      for (const panel of panels) {
        if (!panel.busy) continue;
        nextBusy.set(panel.panelId, panel.sessionId);
        if (!busyPanels.current.has(panel.panelId)) pendingSessions.current.add(panel.sessionId);
      }
      busyPanels.current = nextBusy;
      const busySessions = new Set(nextBusy.values());
      for (const pending of pendingSessions.current) {
        if (!busySessions.has(pending)) pendingSessions.current.delete(pending);
      }
      revealPending();
    });
  }, [desktop, revealPending]);

  useEffect(() => {
    if (!desktop?.isElectron) return;
    let active = true;
    const revision = eventRevision.current;
    // A restored busy panel is a baseline, not evidence of a new task. An IPC
    // event received during this read is newer and must not be overwritten.
    void desktop.browser.listPanels(sessionId).then((panels) => {
      if (!active || eventRevision.current !== revision) return;
      for (const [panelId, owner] of busyPanels.current) {
        if (owner === sessionId) busyPanels.current.delete(panelId);
      }
      for (const panel of panels) {
        if (panel.sessionId === sessionId && panel.busy) {
          busyPanels.current.set(panel.panelId, sessionId);
        }
      }
    }).catch(() => {});
    return () => { active = false; };
  }, [desktop, sessionId]);

  useEffect(() => {
    revealPending();
  }, [headless, sessionId, revealPending]);
}

/**
 * Persist visibility across ToolPanel remounts. An explicit close hides the
 * tab until a new headed task or file preview requests it again.
 */
export function useDesktopBrowserTabFlags(sessionId: string): DesktopBrowserTabFlags {
  const [flags, setFlags] = useState<DesktopBrowserTabFlags>(() => loadDesktopBrowserTabFlags(sessionId));
  useEffect(() => {
    setFlags(loadDesktopBrowserTabFlags(sessionId));
    const handler = () => setFlags(loadDesktopBrowserTabFlags(sessionId));
    window.addEventListener(DESKTOP_BROWSER_TAB_EVENT, handler);
    return () => window.removeEventListener(DESKTOP_BROWSER_TAB_EVENT, handler);
  }, [sessionId]);
  return flags;
}

function isDesktopBrowserPreviewableFile(fileName: string): boolean {
  const extension = fileName.split('.').pop()?.toLowerCase() ?? '';
  return DESKTOP_BROWSER_FILE_EXTENSIONS.has(extension);
}
