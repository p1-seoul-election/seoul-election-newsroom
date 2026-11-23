import { canReleaseDemographics, integrationReadiness } from './analytics';
import type { StatisticsEvidence } from './analytics';
import type { State } from './types';
/** Frontend presentation boundary only. No backend endpoint or demographic bins are specified. */
export interface VerifiedStatisticsView {
  evidence: StatisticsEvidence;
  sourceUrl: string;
  basis: string;
  groups: {label:string;turnoutPct:number}[];
}
export function DemographicAnalytics({state,countRate,statistics}:{state:State;countRate:number;statistics?:VerifiedStatisticsView}) {
  const evidence=statistics?.evidence ?? integrationReadiness.demographics;
  const release=canReleaseDemographics(state,countRate,evidence) && !!statistics && /^https:\/\//.test(statistics.sourceUrl) && !!statistics.basis && statistics.groups.length>0 && statistics.groups.every(g=>!!g.label && Number.isFinite(g.turnoutPct) && g.turnoutPct>=0 && g.turnoutPct<=100);
  return <section className="panel demographics" aria-labelledby="demographics-title"><div className="section-title"><div><span className="eyebrow">OFFICIAL STATISTICS / GATED</span><h2 id="demographics-title">성별·연령별 공식 투표율</h2></div><span className="badge gold">{release?'검증 완료':'공개 잠금'}</span></div>
    {release && statistics ? <div data-testid="demographic-chart">{statistics.groups.map(g=><div className="stat-row" key={g.label}><span>{g.label}</span><meter min={0} max={100} value={g.turnoutPct}/><b>{g.turnoutPct.toFixed(2)}%</b></div>)}<p>{statistics.basis} · <a href={statistics.sourceUrl} target="_blank" rel="noreferrer">공식 출처</a></p></div> : <div data-testid="demographic-lock"><h3>공식 통계 준비 중 · 검증 대기</h3><p>가상 개표 완료와 독립 검증을 모두 마친 뒤 공개합니다.</p><div className="gate-list"><span>{state==='COMPLETED'?'✓':'○'} COMPLETED</span><span>{countRate===100?'✓':'○'} 개표율 100%</span><span>{evidence.available && evidence.electionId==='0020260603' && evidence.officialSourceVerified?'✓':'○'} 2026 공식 통계 확보</span><span>{evidence.independentlyVerified?'✓':'○'} 독립 검증 완료</span></div></div>}
    <p className="chart-note">공식 투표율은 고정된 역사 통계입니다. 후보별 득표율 또는 사전투표자 수로 대체하지 않습니다.</p>
  </section>;
}
