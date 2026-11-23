import type { Frame, Region, State } from './types';
import { catalog } from './validation';

/** Frontend-only derived view models; these are not proposed Backend API fields. */
export function rankCandidates(region: Region) {
  const sorted = [...region.candidate_votes].sort((a,b) => b.votes-a.votes || a.candidate_id.localeCompare(b.candidate_id));
  return sorted.map(c => ({
    ...c, ...catalog.candidates.find(k => k.candidate_id === c.candidate_id)!,
    rank: region.valid_votes > 0 ? 1 + sorted.filter(other => other.votes > c.votes).length : null,
    colorIndex: catalog.candidates.findIndex(k => k.candidate_id === c.candidate_id),
  }));
}
export function leadingGap(region: Region) {
  if (region.valid_votes <= 0) return null;
  const ranked = rankCandidates(region);
  if (ranked.length < 2 || ranked[0].vote_share_pct === null || ranked[1].vote_share_pct === null) return null;
  return { votes: ranked[0].votes-ranked[1].votes, percentagePoints: ranked[0].vote_share_pct-ranked[1].vote_share_pct, tied: ranked[0].votes === ranked[1].votes, first: ranked[0].candidate_name, second: ranked[1].candidate_name };
}
export function priorRanking(history: Frame[], current: Frame) {
  const index = history.findIndex(f => f.run_id === current.run_id && f.snapshot_id === current.snapshot_id && f.seq === current.seq);
  const previous = history.slice(0, index).filter(f => f.run_id === current.run_id && (f.regions?.[0].valid_votes ?? 0) > 0).at(-1);
  return previous ? rankCandidates(previous.regions![0]) : null;
}
export interface StatisticsEvidence {
  available: boolean;
  electionId: string | null;
  officialSourceVerified: boolean;
  independentlyVerified: boolean;
}
export const pendingEvidence: StatisticsEvidence = { available:false, electionId:null, officialSourceVerified:false, independentlyVerified:false };
export function canReleaseDemographics(state: State, countRate: number, evidence: StatisticsEvidence): boolean {
  return state === 'COMPLETED' && countRate === 100 && evidence.available && evidence.electionId === '0020260603' && evidence.officialSourceVerified && evidence.independentlyVerified;
}
export const integrationReadiness = {
  fullReplay: { available: false, proposedDurationSeconds: 180 },
  districtEvents: { available: false },
  historicalTurnout: { available: false, verification: 'REVIEW_REQUIRED' },
  demographics: pendingEvidence,
} as const;
