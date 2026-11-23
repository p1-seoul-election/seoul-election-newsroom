import { useState, useSyncExternalStore } from 'react';
import { createRoot } from 'react-dom/client';
import { MockAdapter } from './mock-adapter';
import { catalog } from './validation';
import { leadingGap, rankCandidates, priorRanking } from './analytics';
import { VoteShareTrend, colors } from './VoteShareTrend';
import { DemographicAnalytics } from './DemographicAnalytics';
import { Diagnostics, Badge, time } from './Diagnostics';
import { usePlaybackClock, formatDuration } from './use-playback-clock';
import type { Command, Scenario } from './types';
import './styles.css';
import './analytics.css';
import './readability.css';
const adapter = new MockAdapter();
const number=(n:number)=>n.toLocaleString('ko-KR');
const scenarios:[Scenario,string][]=[['normal','정상 개표 진행'],['invalid','잘못된 개표 데이터'],['receiver-disconnect','SYSTEM 2 연결 끊김'],['ws-disconnect','FE–SYSTEM 1 연결 끊김'],['ack-wait','ACK 대기'],['lagging','ACK 지연 · LAGGING'],['stale','ACK 시간 초과 · STALE']];
function App(){
 const v=useSyncExternalStore(adapter.subscribe,adapter.getSnapshot);
 const [scenario,setScenario]=useState<Scenario>('normal');
 const [confirm,setConfirm]=useState(false);
 const [requestError,setRequestError]=useState('');
 const [district,setDistrict]=useState('SEOUL_D01');
 const r=v.snapshot.regions![0];
 const ranked=rankCandidates(r),gap=leadingGap(r),previous=priorRanking(v.history,v.snapshot);
 const elapsed=usePlaybackClock(v.run,v.state,v.transport==='CONNECTED');
 const disabled=v.busy||v.transport==='DISCONNECTED';
 const command=async(c:Command)=>{setRequestError('');try{await adapter.command(c);}catch(e){setRequestError(String(e));}};
 const selected=catalog.regions.find(r=>r.region_id===district)!;
 return <div className="shell analytics-shell">
  <header><div className="brand"><span className="brandmark">MBC</span><span className="divider"/><div><div className="eyebrow">ELECTION ANALYTICS & SIMULATION</div><h1>SYSTEM <span>01</span><small>서울시장 선거 분석 대시보드</small></h1></div></div><div className="header-right"><span className="mode">● MOCK DEMO</span><strong>2026 서울시장 선거</strong><span className="backend-status">Backend 미연결</span><Badge value={v.state}/></div></header>
  <div className="notice"><span>교육용 시뮬레이션</span>가상 숫자·연결·ACK 예시입니다. 실제 개표 중계나 역사적 중간 개표 재현이 아닙니다.<b>MOCK · simulated=true · v0.4.1</b></div>
  <section className="panel controls" aria-label="시뮬레이션 제어"><div className="control-top"><div className="control-title"><span className="eyebrow">SIMULATION CONTROL</span><h2>시뮬레이션 제어 <Badge value={v.state}/></h2></div><div className="scenario-select"><label htmlFor="scenario">시연 시나리오</label><select id="scenario" value={scenario} disabled={v.state!=='IDLE'||v.busy} onChange={e=>{const s=e.target.value as Scenario;setScenario(s);adapter.setScenario(s);}}>{scenarios.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></div><div className="buttons"><button className="start" onClick={()=>command('start')} disabled={disabled||!['IDLE','PAUSED'].includes(v.state)}>▶ START</button><button onClick={()=>command('stop')} disabled={disabled||v.state!=='RUNNING'}>■ STOP</button><button className="reset" onClick={()=>setConfirm(true)} disabled={disabled}>↺ RESET</button></div><div className="clock"><label>로컬 시연 재생 시간</label><strong data-testid="playback-clock">{formatDuration(elapsed)}</strong><small>개표율 계산에 사용하지 않음</small></div><div className="future-playback"><b>180초 → 100%</b><span>3분 자동 재생 · 향후 연동 예정</span><small>현재 Fixture 범위 0–20.20%</small></div></div>
  <div className="control-bottom"><span role="status">{v.busy?'MOCK 응답 처리 중…':v.note}</span><code data-testid="run-id">{v.run}</code><button className="connection-toggle" onClick={()=>v.transport==='CONNECTED'?adapter.disconnect():adapter.reconnect()} disabled={v.busy}>{v.transport==='CONNECTED'?'FE 연결 끊기':'MOCK 연결 복구'}</button></div>
  <p className="scenario-hint">다른 시나리오는 RESET 후 선택하세요. STOP은 누적값과 재생 시간을 보존합니다.</p></section>
  {(v.error||requestError||v.stale||['STALE','DISCONNECTED'].includes(v.receiver.receiver_state))&&<div className="alert persistent-alert" role="alert"><strong>{requestError||v.error||'연결·수신 상태 확인 필요'}</strong><span>마지막 정상 데이터 유지 · 갱신시각 {time(v.snapshot.emitted_at)} KST (예시) · {v.transport==='DISCONNECTED'?'FE 연결 끊김 / 오래된 자료':'수신 상태 '+v.receiver.receiver_state}</span></div>}
  <main className="analytics-main">
   <section className="panel candidates"><div className="section-title"><div><span className="eyebrow">01 / CANDIDATE ANALYTICS</span><h2>후보별 득표 현황 <small>SEOUL · 가상 누적값</small></h2></div><span className="scope">후보 5명 / 현재 유효표 기준</span></div>
    <div className="overview"><div className="progress-head"><div><label>서울 전체 가상 개표율</label><div className="big-number" data-testid="count-rate">{r.count_rate_pct.toFixed(2)}<span>%</span></div></div><div className="target"><span>교육용 목표</span><strong>{number(r.target_ballots)} <small>표</small></strong></div></div>
    <div className="overview-stats"><div><label>누적 개표수</label><strong data-testid="counted">{number(r.counted_votes)}<small>표</small></strong></div><div><label>유효표 / 무효표</label><strong>{number(r.valid_votes)} <small>/ {number(r.invalid_votes)}표</small></strong></div></div>
    <div className="gap" data-testid="candidate-gap"><label>선두 두 후보 격차</label>{gap?<><strong>{number(gap.votes)}<small>표 · {gap.percentagePoints.toFixed(2)}%p</small></strong><span>{gap.tied?'공동 선두 · 동률':gap.first+' ↔ '+gap.second}</span></>:<><strong>비교 불가</strong><span>유효표 집계 대기</span></>}</div></div>
    <div className="progress-track" role="progressbar" aria-label="서울 전체 개표 진행률" aria-valuemin={0} aria-valuemax={100} aria-valuenow={r.count_rate_pct}><div style={{width:r.count_rate_pct+'%'}}/></div><div className="ticks"><span>0%</span><span>현재 제공 범위 20.20%</span><span>100% · 데이터 준비 중</span></div>
    <div className="candidate-table"><div className="candidate-heading"><span>순위 / 후보</span><span>득표 분포 · 현재 유효표 대비</span><span>누적 득표수</span><span>득표율</span></div>{ranked.map(c=>{const prior=previous?.find(p=>p.candidate_id===c.candidate_id);const delta=prior?.rank&&c.rank?prior.rank-c.rank:null;return <div className="candidate-row" key={c.candidate_id} data-testid={'candidate-'+c.ballot_number}><div className="candidate-name"><span className="rank">{c.rank??'—'}<small>{delta===null?'기준 없음':delta===0?'유지':delta>0?'↑'+delta:'↓'+Math.abs(delta)}</small></span><span className="candidate-dot" style={{background:colors[c.colorIndex]}}/><div><strong>{c.candidate_name}<small>기호 {c.ballot_number} · {c.party_name}</small></strong><code>{c.candidate_id}</code></div></div><div className="candidate-bar" role="meter" aria-label={c.candidate_name+' 득표율'} aria-valuemin={0} aria-valuemax={100} aria-valuenow={c.vote_share_pct??undefined} aria-valuetext={c.vote_share_pct===null?'비율 없음':c.vote_share_pct.toFixed(2)+'%'}><div style={{width:(c.vote_share_pct??0)+'%',background:colors[c.colorIndex]}}/></div><strong>{number(c.votes)}<small> 표</small></strong><strong>{c.vote_share_pct===null?'—':c.vote_share_pct.toFixed(2)+'%'}</strong></div>;})}</div>
    <VoteShareTrend history={v.history}/>
    <div className="snapshot" aria-label="Snapshot Reference"><span>SNAPSHOT REFERENCE</span><code>{v.run}</code><code>{v.snapshot.snapshot_id}</code><span>DATA SEQ {v.snapshot.seq} / EVENT SEQ {v.cursor}</span><span>{time(v.snapshot.event_time)} KST (예시)</span></div>
   </section>
   <section className="panel district-analytics"><div className="section-title"><div><span className="eyebrow">02 / SEOUL DISTRICTS</span><h2>25개 자치구 분석</h2></div><span className="badge gold">수신 데이터 0 / 25</span></div><p className="district-notice">전체 25개 구의 시뮬레이션 데이터 준비 중 · 공식 최종 결과로 대체하지 않습니다.</p>
    <div className="district-grid" role="group" aria-label="서울 자치구 선택">{catalog.regions.filter(r=>r.region_level==='DISTRICT').map(r=><button key={r.region_id} aria-label={r.region_name+' 준비 중'} aria-pressed={district===r.region_id} onClick={()=>setDistrict(r.region_id)}><strong>{r.region_name}</strong></button>)}</div>
    <div className="district-detail" aria-live="polite"><div><strong>{selected.region_name}</strong><code>{selected.region_id}</code></div><h3>시뮬레이션 데이터 준비 중</h3><div className="district-metrics"><span>개표율 <b>—</b></span><span>선두 후보 <b>—</b></span><span>득표 격차 <b>—</b></span></div><p>후보별 득표 분포·지역 비교·진행 속도는 실제 지역별 이벤트 수신 후 표시합니다.</p></div>
    <p className="chart-note">CITY와 DISTRICT 이중 합산 금지 · 현재 MOCK은 서울 전체 1개 지역만 제공합니다.</p>
   </section>
   <section className="panel historical"><div className="section-title"><div><span className="eyebrow">03 / HISTORICAL TURNOUT</span><h2>실제 시간대별 투표율</h2></div><span className="badge gold">REVIEW_REQUIRED</span></div><div className="pending-data"><span className="pending-symbol">◷</span><div><h3>실제 시간대별 투표율 데이터 검증 중</h3><p>2026.06.03 · 07:00–18:00 KST · 공식 원본·출처·분모 확인 전 수치 비공개</p></div></div><p className="chart-note">가상 개표와 별도 분석입니다. 미제공 08시 값을 보간하지 않으며, 13시 사전투표 등 합산 여부는 원본 대조 후 설명합니다.</p></section>
   <DemographicAnalytics state={v.state} countRate={r.count_rate_pct}/>
  </main>
  <Diagnostics view={v}/>
  <footer><span>MBC AI 데이터 저널리즘 PROJECT 1 · SYSTEM 1 FRONTEND v0.4.1</span><span>API v0.1 제안 / 참조 데이터 REVIEW_REQUIRED / 실제 Backend 미연결</span></footer>
  {confirm&&<div className="modal-backdrop"><section role="dialog" aria-modal="true" aria-labelledby="reset-title" className="modal" onKeyDown={e=>{if(e.key==='Escape')setConfirm(false);}}><span className="eyebrow">RESET SIMULATION</span><h2 id="reset-title">새 실행으로 초기화할까요?</h2><p>0표·새 run_id로 시작하고 현재 실행의 추이와 로컬 재생 시간을 초기화합니다. 이전 이벤트 로그는 유지합니다.</p><div className="buttons"><button autoFocus onClick={()=>setConfirm(false)}>취소</button><button className="reset" onClick={()=>{setConfirm(false);command('reset');}}>초기화 확인</button></div></section></div>}
 </div>;
}
createRoot(document.getElementById('root')!).render(<App/>);

