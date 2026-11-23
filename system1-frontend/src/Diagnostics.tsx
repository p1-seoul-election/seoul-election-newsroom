import { useState } from 'react';
import type { View } from './types';
export function Badge({ value }: { value: string }) { return <span className={'badge ' + (['ERROR','DISCONNECTED','REJECTED','STALE'].includes(value) ? 'red' : ['RUNNING','SYNCED','CONNECTED','APPLIED','COMPLETED'].includes(value) ? 'green' : 'gold')}>{value}</span>; }
export const time = (s?: string | null) => s ? new Date(s).toLocaleTimeString('ko-KR', { hour12: false, timeZone: 'Asia/Seoul' }) : '—';
export function Diagnostics({view:v}:{view:View}) {
  const [filter,setFilter]=useState('all');
  const logs=[...v.logs].reverse().filter(l=>filter==='all'||l.frame.type===filter);
  return <details className="panel diagnostics" data-testid="diagnostics"><summary><div><span className="eyebrow">SYSTEM DIAGNOSTICS</span><strong>연결 · ACK · 이벤트 로그</strong></div><span className="diag-summary">FE {v.transport} · S2 {v.receiver.receiver_state} · {v.logs.length} EVENTS</span><span className="expand-label">상세 열기 / 닫기</span></summary><div className="diagnostic-content">
    <section className="receiver"><div className="section-title"><h2>SYSTEM 2 수신 모니터</h2><Badge value={v.receiver.receiver_state}/></div>
      <dl><div><dt>SYSTEM 2 transport</dt><dd>{v.receiver.transport}</dd></div><div><dt>마지막 송신 / ACK seq</dt><dd>{v.receiver.last_sent_seq} / {v.receiver.last_acked_seq??'—'}</dd></div><div><dt>미확인 데이터 버전</dt><dd>{v.receiver.ack_lag_events??'—'}</dd></div><div><dt>최근 ACK (예시 KST)</dt><dd>{time(v.receiver.last_ack_at)}</dd></div><div><dt>ACK / heartbeat 임계값</dt><dd>10s / 15s</dd></div><div><dt>FE WebSocket</dt><dd>{v.transport}</dd></div></dl>
      <div className="evidence">evidence_mode = FIXTURE · live_verified = false</div><p className="chart-note">연결과 저장 완료 ACK는 별개입니다. SYNCED도 가상 예시이며 실제 SYSTEM 2 저장 성공이 아닙니다.</p>
    </section>
    <section className="events"><div className="section-title"><h2>이벤트 스트림 모니터</h2><label className="event-filter">이벤트 필터<select value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">전체 이벤트</option>{['snapshot','update','status','error'].map(t=><option key={t}>{t}</option>)}</select></label></div>
      <div className="event-scroll"><table><thead><tr><th>SEQ</th><th>TYPE</th><th>발생 / 송출 (예시 KST)</th><th>RUN ID</th><th>처리 상태</th><th>상세 / 오류</th></tr></thead><tbody>{logs.length?logs.map(l=><tr key={l.id}><td>{l.frame.seq}</td><td>{l.frame.type}</td><td>{time(l.frame.event_time)} / {time(l.frame.emitted_at)}</td><td><code>{l.frame.run_id}</code></td><td><Badge value={l.outcome}/></td><td>{l.message || (l.frame.error?l.frame.error.code+' · '+l.frame.error.message:l.frame.reason||l.frame.snapshot_id)}</td></tr>):<tr><td colSpan={6} className="empty">이벤트 대기 중 · START로 시연을 시작하세요.</td></tr>}</tbody></table></div>
      <p className="chart-note">최신 수신 순 · 최근 200개 보관 · RESET 후 이전 실행 로그 보존 · 원본 예시 시각 유지</p>
    </section>
  </div></details>;
}
