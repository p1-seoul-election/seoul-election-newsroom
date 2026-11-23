import type { Adapter, Command, View, Frame } from './types';
import { initialView, receive } from './mock-adapter';
export interface LiveConfig { restBaseUrl: string; wsUrl: string; fetcher?: typeof fetch }
/** Contract v0.1 PROPOSAL ONLY. Not selected by the demo UI; no live success claimed. */
export class RestWebSocketAdapter implements Adapter {
  private value: View = { ...initialView(), transport: 'DISCONNECTED', stale: true, note: 'Backend 미연결 · API Contract v0.1 제안' };
  private listeners = new Set<() => void>();
  private socket?: WebSocket;
  private retry?: ReturnType<typeof setTimeout>;
  private attempts = 0;
  private closed = true;
  private syncing = true;
  private retiredRuns = new Set<string>();
  constructor(private config: LiveConfig) {}
  getSnapshot = () => this.value;
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; };
  private set(v: Partial<View>) { this.value = { ...this.value, ...v }; this.listeners.forEach(fn => fn()); }
  connect() {
    this.closed = false; this.syncing = true;
    this.socket = new WebSocket(this.config.wsUrl);
    this.socket.onmessage = event => {
      try {
        const f = JSON.parse(event.data) as Frame;
        if (this.retiredRuns.has(f.run_id)) return;
        if (this.syncing && f.type !== 'snapshot') return;
        const next = receive(this.value, f, this.syncing && f.type === 'snapshot');
        if (next.error?.startsWith('SEQ_GAP') || next.error?.startsWith('RUN_MISMATCH')) { this.set(next); this.socket?.close(); return; }
        if (next.logs.at(-1)?.outcome === 'APPLIED') { this.syncing = false; this.attempts = 0; }
        this.set({ ...next, transport: 'CONNECTED', note: 'REST / WebSocket 어댑터 · 수신 상태' });
      } catch { this.set({ error: 'INVALID_JSON: 마지막 정상 데이터 유지', stale: true }); }
    };
    this.socket.onerror = () => this.socket?.close();
    this.socket.onclose = () => {
      this.set({ transport: 'DISCONNECTED', stale: true });
      if (!this.closed) this.retry = setTimeout(() => this.connect(), Math.min(1000 * 2 ** this.attempts++, 10000));
    };
  }
  async command(command: Command) {
    if (this.value.busy) return;
    this.set({ busy: true });
    const request_id = crypto.randomUUID();
    const body = { request_id, expected_run_id: this.value.run, ...(command === 'start' ? { election_id: '0020260603', election_type: 'GOVERNOR', scenario_id: 'MOCK_SEOUL_10000_V01', data_mode: 'MOCK', simulated: true } : {}) };
    try {
      const response = await (this.config.fetcher ?? fetch)(this.config.restBaseUrl + '/simulation/' + command, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: AbortSignal.timeout(10000) });
      const result = await response.json();
      if (!response.ok || result.ok !== true) throw new Error(result.error?.message ?? '제어 요청 실패');
      if (result.request_id !== request_id || typeof result.run_id !== 'string' || !['IDLE','RUNNING','PAUSED','COMPLETED','ERROR'].includes(result.state)) throw new Error('제어 응답 계약 불일치');
      if (command === 'reset') {
        const status = await (this.config.fetcher ?? fetch)(this.config.restBaseUrl + '/simulation/status', { signal: AbortSignal.timeout(10000) });
        if (!status.ok) throw new Error('RESET 응답 후 snapshot 동기화 필요');
        const current = await status.json();
        if (!current.ok || current.run_id !== result.run_id || current.snapshot?.run_id !== result.run_id) throw new Error('RESET snapshot 실행 불일치');
        const snapshot = { ...current.snapshot, type: 'snapshot', sync_cursor_seq: current.seq, system2: current.system2 } as Frame;
        const next = receive(this.value, snapshot, true);
        if (next.logs.at(-1)?.outcome !== 'APPLIED') throw new Error(next.error ?? 'RESET snapshot 검증 실패');
        this.retiredRuns.add(this.value.run);
        this.set(next);
      } else this.set({ state: result.state, error: null });
    } catch (error) {
      this.set({ error: error instanceof Error ? error.message : '요청 실패', ...(command === 'reset' ? { stale: true } : {}) });
      throw error;
    } finally { this.set({ busy: false }); }
  }
  dispose() { this.closed = true; clearTimeout(this.retry); this.socket?.close(); this.listeners.clear(); }
}
