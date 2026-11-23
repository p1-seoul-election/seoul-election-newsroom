import fixture from './fixtures/mock-v0.1.json';
import type { Frame, Region } from './types';
export const catalog = fixture.catalog;
const integer = (v: unknown) => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0;
const ratio = (v: unknown, expected: number) => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 100 && Math.abs(v - expected) < 0.0000011;
export function validateFrame(input: unknown, previous?: Frame): string | null {
  if (!input || typeof input !== 'object') return 'INVALID_MESSAGE: JSON 객체가 아닙니다.';
  const f = input as Frame;
  if (f.contract_version !== '0.1' || f.contract_status !== 'PROPOSAL_UNIMPLEMENTED' || f.election_id !== '0020260603' || f.election_type !== 'GOVERNOR' || f.data_mode !== 'MOCK' || f.simulated !== true) return 'INVALID_ENVELOPE: 계약 또는 교육용 데이터 고지 불일치';
  if (!['snapshot','update','status','error'].includes(f.type) || !['IDLE','RUNNING','PAUSED','COMPLETED','ERROR'].includes(f.state) || !f.run_id || typeof f.run_id !== 'string' || !integer(f.seq) || f.seq < 1) return 'INVALID_ENVELOPE: 종류·상태·실행·순번 오류';
  if (!f.notice || !f.reference || f.reference.verification_status !== 'REVIEW_REQUIRED' || f.reference.results_as_of !== null || f.reference.results_as_of_precision !== 'UNKNOWN' || ![f.event_time,f.emitted_at].every(t => typeof t === 'string' && Number.isFinite(Date.parse(t)))) return 'INVALID_METADATA';
  if (f.type === 'error' && (!f.error?.code || !f.error?.message)) return 'INVALID_ERROR';
  if (f.type !== 'snapshot' && f.type !== 'update') return null;
  if (!f.snapshot_id || f.scope_region_ids?.length !== 1 || f.scope_region_ids[0] !== 'SEOUL' || !Array.isArray(f.regions) || f.regions.length !== 1) return 'INVALID_SCOPE';
  const r: Region = f.regions[0];
  if (r.region_id !== 'SEOUL' || r.target_ballots_basis !== 'SCENARIO_FIXED_EDUCATIONAL') return 'UNKNOWN_ID: 지역 또는 목표 기준';
  if (![r.target_ballots,r.counted_votes,r.valid_votes,r.invalid_votes].every(integer) || r.target_ballots < 1 || r.counted_votes > r.target_ballots) return 'INVALID_NUMBER';
  if (r.counted_votes !== r.valid_votes + r.invalid_votes) return 'TOTAL_MISMATCH: 유효표 + 무효표 ≠ 누적 개표수';
  if (!ratio(r.count_rate_pct, r.counted_votes / r.target_ballots * 100)) return 'INVALID_COUNT_RATE';
  if (!Array.isArray(r.candidate_votes) || r.candidate_votes.length !== catalog.candidates.length || new Set(r.candidate_votes.map(c => c.candidate_id)).size !== catalog.candidates.length) return 'INVALID_CANDIDATES';
  for (const c of r.candidate_votes) {
    if (!catalog.candidates.some(k => k.candidate_id === c.candidate_id)) return 'UNKNOWN_ID: 후보';
    if (!integer(c.votes) || (r.valid_votes === 0 ? c.vote_share_pct !== null : !ratio(c.vote_share_pct, c.votes / r.valid_votes * 100))) return 'INVALID_VOTE_SHARE';
  }
  if (r.candidate_votes.reduce((n,c) => n + c.votes, 0) !== r.valid_votes) return 'TOTAL_MISMATCH: 후보 합계';
  if (previous?.run_id === f.run_id && previous.regions) {
    const p = previous.regions[0];
    if (r.target_ballots !== p.target_ballots || r.counted_votes < p.counted_votes || r.invalid_votes < p.invalid_votes || r.candidate_votes.some(c => c.votes < (p.candidate_votes.find(x => x.candidate_id === c.candidate_id)?.votes ?? 0))) return 'CUMULATIVE_DECREASE';
  }
  if (f.type === 'snapshot' && (!integer(f.sync_cursor_seq) || f.sync_cursor_seq! < f.seq)) return 'INVALID_SYNC_CURSOR';
  return null;
}
