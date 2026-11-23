import fixture from './fixtures/mock-v0.1.json';
import type { Frame, View, Receiver, Adapter, Command, Scenario } from './types';
import { validateFrame } from './validation';

export const copy = <T,>(v: T): T => structuredClone(v);
export const normal = fixture.scenarios.normal.frames as Frame[];
export function initialView(): View {
  const snapshot = copy(normal[0]);
  const receiver = copy(normal[1].system2!);
  receiver.last_sent_seq = 1;
  receiver.last_heartbeat_at = null;
  return { state: 'IDLE', run: snapshot.run_id, cursor: 1, snapshot, history: [copy(snapshot)], receiver, transport: 'CONNECTED', stale: false, logs: [], error: null, lastEvent: snapshot, busy: false, note: '원본 Fixture 재생 준비 · 실제 서버 연결 없음' };
}
export function receive(view: View, input: unknown, resync = false): View {
  const f = input as Frame;
  const problem = validateFrame(input, resync && f?.run_id !== view.run ? undefined : view.snapshot);
  const log = (outcome: 'APPLIED' | 'REJECTED' | 'IGNORED', message?: string) => [...view.logs, { id: (view.logs.at(-1)?.id ?? 0) + 1, frame: f, outcome, message, observed_at: new Date().toISOString() }].slice(-200);
  if (problem) return { ...view, state: 'ERROR', error: problem, stale: true, logs: log('REJECTED', problem) };
  if (f.run_id !== view.run && !(f.type === 'snapshot' && resync)) return { ...view, stale: true, error: 'RUN_MISMATCH: 최신 snapshot 필요', logs: log('REJECTED', '다른 실행') };
  if (f.run_id === view.run && f.seq <= view.cursor && !resync) return { ...view, logs: log('IGNORED', '중복·역행 이벤트') };
  if (!resync && f.seq !== view.cursor + 1) return { ...view, stale: true, error: 'SEQ_GAP: 최신 snapshot 필요', logs: log('REJECTED', '순번 누락') };
  const data = f.type === 'snapshot' || f.type === 'update';
  let receiver = copy(f.system2 ?? view.receiver);
  if (data && !f.system2) {
    receiver = { ...receiver, run_id: f.run_id, last_sent_seq: f.seq, receiver_state: receiver.last_acked_seq === null ? 'AWAITING_ACK' : 'LAGGING', ack_lag_events: receiver.last_acked_seq === null ? null : (receiver.ack_lag_events ?? 0) + 1 };
  }
  // Fixture evidence must never imply successful live verification.
  if (receiver.evidence_mode === 'FIXTURE') receiver.live_verified = false;
  return { ...view, state: f.state, run: f.run_id, cursor: f.type === 'snapshot' ? f.sync_cursor_seq! : f.seq, snapshot: data ? copy(f) : view.snapshot, history: data ? (f.run_id !== view.run ? [copy(f)] : view.history.some(p => p.snapshot_id === f.snapshot_id && p.seq === f.seq) ? view.history : [...view.history, copy(f)]) : view.history, receiver, lastEvent: copy(f), stale: f.type === 'error', error: f.error ? f.error.code + ': ' + f.error.message : null, logs: log('APPLIED') };
}
export class MockAdapter implements Adapter {
  private value = initialView();
  private listeners = new Set<() => void>();
  private timer?: ReturnType<typeof setTimeout>;
  private stage = 0;
  private disposed = false;
  scenario: Scenario = 'normal';
  getSnapshot = () => this.value;
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; };
  private publish(v: View) { this.value = v; this.listeners.forEach(fn => fn()); }
  private patch(v: Partial<View>) { this.publish({ ...this.value, ...v }); }
  private cancel() { clearTimeout(this.timer); this.timer = undefined; }
  private frame(template: Frame): Frame {
    const f = copy(template);
    f.run_id = this.value.run;
    f.seq = this.value.cursor + 1;
    if (f.snapshot_id) f.snapshot_id = f.run_id + '_S' + f.seq;
    delete f.sync_cursor_seq;
    if (f.type === 'snapshot') f.sync_cursor_seq = f.seq;
    if (f.system2) f.system2.run_id = f.run_id;
    return f;
  }
  private emit(f: Frame) { this.publish(receive(this.value, f)); }
  setScenario(s: Scenario) { if (!this.value.busy && this.value.state !== 'RUNNING') { this.scenario = s; this.patch({ note: '시연 시나리오 선택됨 · 숫자는 원본 Fixture 사용' }); } }
  async command(cmd: Command) {
    if (this.value.busy || this.disposed) return;
    if (this.value.transport !== 'CONNECTED') throw new Error('연결 복구 후 제어하세요.');
    if (cmd === 'start' && !['IDLE','PAUSED'].includes(this.value.state)) throw new Error('RESET_REQUIRED');
    this.patch({ busy: true });
    this.cancel();
    // Asynchronous local response only. No network or backend is involved.
    await new Promise(resolve => setTimeout(resolve, 120));
    if (this.disposed) return;
    if (cmd === 'reset') {
      this.stage = 0;
      const f = copy(fixture.scenarios.reset.frame) as Frame;
      f.run_id = 'MOCK_RUN_' + crypto.randomUUID().slice(0,8);
      f.snapshot_id = f.run_id + '_S1';
      f.system2!.run_id = f.run_id;
      f.system2!.last_heartbeat_at = null;
      this.publish({ ...receive(this.value, f, true), busy: false, transport: 'CONNECTED', stale: false, note: '새 실행 · 0표 · ACK 대기 (MOCK)' });
      return;
    }
    if (cmd === 'stop') {
      if (this.value.state === 'RUNNING') this.emit(this.frame(fixture.scenarios.normal.stop_frame as Frame));
      this.patch({ busy: false, note: '일시 중지 · 누적값과 run_id 보존' });
      return;
    }
    const start = this.frame(normal[1]);
    start.system2 = copy(this.value.receiver);
    this.emit(start);
    this.patch({ busy: false, note: this.stage >= 2 ? '제공 Fixture의 마지막 데이터(20.20%)입니다. 추가 가상 수치를 생성하지 않습니다.' : '원본 Fixture 재생 중 · 로컬 가상 이벤트' });
    this.schedule();
  }
  private schedule() { this.timer = setTimeout(() => this.tick(), 1400); }
  private tick() {
    if (this.disposed || this.value.state !== 'RUNNING' || this.value.transport !== 'CONNECTED') return;
    if (this.stage === 0) {
      this.emit(this.frame(normal[2]));
      this.stage = 1;
      this.schedule();
      return;
    }
    if (this.stage === 1) {
      this.stage = 2;
      if (this.scenario === 'invalid') {
        this.emit(this.frame(fixture.scenarios.error.invalid_incoming_update as Frame));
        const error = this.frame(fixture.scenarios.error.frame as Frame);
        error.last_good_snapshot_id = this.value.snapshot.snapshot_id;
        this.emit(error);
        this.patch({ note: '잘못된 2,019표 차단 · 마지막 정상 2,020표 유지' });
        return;
      }
      if (this.scenario === 'receiver-disconnect') {
        const f = this.frame(fixture.scenarios.disconnected.frame as Frame);
        f.system2 = { ...this.value.receiver, transport: 'DISCONNECTED', receiver_state: 'DISCONNECTED' };
        this.emit(f);
        this.patch({ stale: true, note: 'SYSTEM 2 연결 끊김 시연 · 생성 중단 / RESET 필요' });
        return;
      }
      if (this.scenario === 'ws-disconnect') { this.disconnect(); return; }
      if (['ack-wait','lagging','stale'].includes(this.scenario)) {
        const receiver = copy(this.value.receiver);
        receiver.receiver_state = this.scenario === 'ack-wait' ? 'AWAITING_ACK' : this.scenario === 'lagging' ? 'LAGGING' : 'STALE';
        if (this.scenario !== 'ack-wait') {
          receiver.last_acked_seq = 1; receiver.last_ack_at = normal[0].emitted_at; receiver.ack_lag_events = 1;
        }
        const f = this.frame(normal[3]); f.system2 = receiver; f.reason = 'DEMO_RECEIVER_' + receiver.receiver_state;
        this.emit(f);
      } else {
        const f = this.frame(normal[3]);
        f.system2 = { ...this.value.receiver, receiver_state: 'SYNCED', last_sent_seq: this.value.snapshot.seq, last_acked_seq: this.value.snapshot.seq, last_ack_at: normal[3].system2!.last_ack_at, ack_lag_events: 0, evidence_mode: 'FIXTURE', live_verified: false };
        this.emit(f);
      }
      this.schedule();
      return;
    }
    this.emit(this.frame(fixture.scenarios.normal.stop_frame as Frame));
    this.patch({ note: 'Fixture 재생 완료 · 20.20%에서 일시 중지. 100% 데이터는 제공되지 않았습니다.' });
  }
  disconnect() { this.cancel(); this.patch({ transport: 'DISCONNECTED', stale: true, note: 'FE–SYSTEM 1 소켓 close 시연 · 마지막 정상 데이터 유지' }); }
  reconnect() {
    const f = copy(this.value.snapshot);
    f.type = 'snapshot'; f.sync_cursor_seq = this.value.cursor; f.state = this.value.state; f.system2 = copy(this.value.receiver);
    this.publish({ ...receive(this.value, f, true), transport: 'CONNECTED', stale: this.value.state === 'ERROR', note: 'MOCK 최신 snapshot 재동기화 · 실제 서버 연결 없음' });
    if (this.value.state === 'RUNNING') this.schedule();
  }
  dispose() { this.disposed = true; this.cancel(); this.listeners.clear(); }
}

