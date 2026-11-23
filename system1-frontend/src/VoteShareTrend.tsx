import type { Frame } from './types';
import { catalog } from './validation';
export const colors = ['#79a8d9','#c78ba1','#c5aa73','#a998d5','#7fb9aa'];
const stamp = (s:string) => new Date(s).toLocaleTimeString('en-GB',{hour12:false,timeZone:'Asia/Seoul'});
/** Each marker is one actual accepted snapshot. Null values are gaps, never zero. */
export function VoteShareTrend({history}:{history:Frame[]}) {
  const w=650,h=180,left=65,right=30,top=16,bottom=30;
  const percent=(coordinate:number)=>coordinate/w*100+'%';
  const times=history.map(f=>Date.parse(f.event_time));
  const min=Math.min(...times),max=Math.max(...times);
  const x=(i:number)=> max===min ? w/2 : left+(times[i]-min)/(max-min)*(w-left-right);
  const y=(pct:number)=>top+(100-pct)/100*(h-top-bottom);
  const valid=history.filter(f=>(f.regions?.[0].valid_votes ?? 0)>0).length;
  return <div className="trend" data-testid="trend" data-observations={history.length} data-valid-observations={valid}>
    <div className="trend-heading"><h3>득표율 변화 <small>Vote Share Trend</small></h3><span>수신 {history.length}시점 · 유효 비율 {valid}시점</span></div>
    <svg width="100%" height={h} role="img" aria-label={'후보별 득표율 추이, 수신 '+history.length+'시점. 유효표 0 시점의 득표율은 null이며 연결하지 않습니다.'}>
      {[0,25,50,75,100].map(p=><g key={p}><line x1={percent(left)} x2={percent(w-right)} y1={y(p)} y2={y(p)} className="grid-line"/><text x={percent(left-14)} y={y(p)+4} textAnchor="end">{p}</text></g>)}
      {history.map((f,i)=><g key={f.snapshot_id+':'+f.seq}><line x1={percent(x(i))} x2={percent(x(i))} y1={top} y2={h-bottom} className="time-line"/><text x={percent(x(i))} y={h-7} textAnchor={x(i)<=left?'start':x(i)>=w-right?'end':'middle'}>{stamp(f.event_time)}</text>{f.regions![0].valid_votes===0 && <text x={percent(x(i)+10)} y={h/2-12} textAnchor="start">비율 없음</text>}</g>)}
      {catalog.candidates.map((c,ci)=>{
        const values=history.map(f=>f.regions?.[0].candidate_votes.find(v=>v.candidate_id===c.candidate_id)?.vote_share_pct ?? null);
        return <g key={c.candidate_id} stroke={colors[ci]} fill={colors[ci]}>
          {values.map((p,i)=>p!==null && <g key={i}>
            {i>0 && values[i-1]!==null && times[i]>times[i-1] && <line x1={percent(x(i-1))} y1={y(values[i-1]!)} x2={percent(x(i))} y2={y(p)} strokeWidth={2}/>}
            <circle cx={percent(x(i))} cy={y(p)} r={ci===3?6:3.5} fill={ci===3?'none':colors[ci]} strokeWidth={2}><title>{c.candidate_name+' · '+stamp(history[i].event_time)+' · '+p.toFixed(2)+'% · '+history[i].snapshot_id}</title></circle>
          </g>)}
        </g>;
      })}
    </svg>
    <div className="chart-legend">{catalog.candidates.map((c,i)=><span key={c.candidate_id}><i style={{background:colors[i]}}/>{c.candidate_name}</span>)}</div>
    <p className="chart-note">초기 0표는 null입니다. 유효 비율이 1시점뿐이면 점만 표시합니다. 선은 수신점 연결이며 중간 관측값을 생성하지 않습니다.</p>
    <details className="observations"><summary>수신 시점 원자료 확인</summary><div className="table-scroll"><table><thead><tr><th>기준시각 (예시 KST)</th><th>snapshot / seq</th>{catalog.candidates.map(c=><th key={c.candidate_id}>{c.candidate_name}</th>)}</tr></thead><tbody>{history.map(f=><tr key={f.snapshot_id+':'+f.seq}><td>{stamp(f.event_time)}</td><td>{f.snapshot_id} / {f.seq}</td>{catalog.candidates.map(c=><td key={c.candidate_id}>{f.regions![0].candidate_votes.find(v=>v.candidate_id===c.candidate_id)?.vote_share_pct === null ? 'null' : (f.regions![0].candidate_votes.find(v=>v.candidate_id===c.candidate_id)?.vote_share_pct?.toFixed(2) ?? '—')+'%'}</td>)}</tr>)}</tbody></table></div></details>
  </div>;
}



