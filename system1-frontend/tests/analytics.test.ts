import { describe,it,expect } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { leadingGap,rankCandidates,priorRanking,canReleaseDemographics,pendingEvidence } from '../src/analytics';
import { DemographicAnalytics } from '../src/DemographicAnalytics';
import { VoteShareTrend } from '../src/VoteShareTrend';
import { initialView,receive,normal,copy } from '../src/mock-adapter';
import fixture from '../src/fixtures/mock-v0.1.json';
import type { State,Frame } from '../src/types';
const zero=normal[0].regions![0],counted=normal[2].regions![0];
const ready={available:true,electionId:'0020260603',officialSourceVerified:true,independentlyVerified:true};
describe('Derived election analytics',()=>{
 it('reports no rank/gap before valid votes and correct 100 votes / 5 percentage points after',()=>{
  expect(leadingGap(zero)).toBeNull();expect(rankCandidates(zero).every(c=>c.rank===null)).toBe(true);
  expect(leadingGap(counted)).toMatchObject({votes:100,percentagePoints:5,tied:false});
  expect(rankCandidates(counted).map(c=>c.rank)).toEqual([1,2,3,4,4]);
 });
 it('uses joint ranks and neutral ballot-ID ordering for ties',()=>{
  const r=copy(counted);r.candidate_votes[1].votes=1000;r.candidate_votes[1].vote_share_pct=50;
  expect(rankCandidates(r).slice(0,2).map(c=>c.rank)).toEqual([1,1]);
  expect(leadingGap(r)?.tied).toBe(true);
 });
 it('stores only accepted data versions, not status/rejected/duplicates/resync points',()=>{
  let v=initialView();expect(v.history).toHaveLength(1);
  v=receive(v,normal[1]);expect(v.history).toHaveLength(1);
  v=receive(v,normal[2]);expect(v.history).toHaveLength(2);
  expect(priorRanking(v.history,v.snapshot)).toBeNull();
  v=receive(v,normal[3]);expect(v.history).toHaveLength(2);
  v=receive(v,normal[2]);expect(v.history).toHaveLength(2);
  const resync={...copy(v.snapshot),type:'snapshot',sync_cursor_seq:v.cursor} as Frame;
  v=receive(v,resync,true);expect(v.history).toHaveLength(2);
  const bad=copy(fixture.scenarios.error.invalid_incoming_update) as Frame;bad.seq=v.cursor+1;
  v=receive(v,bad);expect(v.history).toHaveLength(2);expect(v.snapshot.regions![0].counted_votes).toBe(2020);
 });
 it('resets history to new run while preserving old event logs',()=>{
  let v=receive(receive(initialView(),normal[1]),normal[2]);
  v=receive(v,fixture.scenarios.reset.frame,true);
  expect(v.history).toHaveLength(1);expect(v.history[0].run_id).toBe('MOCK_RUN_B');expect(v.logs.some(l=>l.frame.run_id==='MOCK_RUN_A')).toBe(true);
 });
 it('shows exactly two observation times, one valid point per candidate and no fabricated line',()=>{
  const html=renderToStaticMarkup(createElement(VoteShareTrend,{history:[normal[0],normal[2]]}));
  expect(html).toContain('data-observations="2"');expect(html).toContain('data-valid-observations="1"');
  expect((html.match(/<circle /g)||[]).length).toBe(5);expect(html).not.toContain('stroke-width="2" x1=');
  expect(html).not.toContain('null%');
 });
 it('handles COMPLETED received state without manufacturing completion in the demo',()=>{
  // TEST ONLY: validates contract state handling, not a new demo dataset.
  const completed={...copy(normal[3]),seq:4,state:'COMPLETED'} as Frame;
  const v=receive(receive(receive(initialView(),normal[1]),normal[2]),completed);
  expect(v.state).toBe('COMPLETED');expect(v.snapshot.regions![0].count_rate_pct).toBe(20.2);
  expect(canReleaseDemographics(v.state,20.2,ready)).toBe(false);
 });
});
describe('Official demographic disclosure gate',()=>{
 it.each(['IDLE','RUNNING','PAUSED','ERROR'] as State[])('blocks %s even when 100%% and verified',state=>{
  expect(canReleaseDemographics(state,100,ready)).toBe(false);
 });
 it.each([0,20.2,99.99,NaN,Infinity,101])('blocks incomplete/invalid rate %s',rate=>{
  expect(canReleaseDemographics('COMPLETED',rate,ready)).toBe(false);
 });
 it('blocks missing statistics, wrong election, unverified source, or missing independent review at 100%',()=>{
  for(const evidence of [pendingEvidence,{...ready,available:false},{...ready,electionId:'2022'},{...ready,officialSourceVerified:false},{...ready,independentlyVerified:false}]){
   expect(canReleaseDemographics('COMPLETED',100,evidence)).toBe(false);
  }
  expect(canReleaseDemographics('COMPLETED',100,ready)).toBe(true);
 });
 it('does not put hidden statistics into HTML before release, even at unverified 100%',()=>{
  const statistics={evidence:{...ready,independentlyVerified:false},sourceUrl:'https://example.org/test-only',basis:'TEST ONLY',groups:[{label:'TEST_PRIVATE_GROUP',turnoutPct:73.12}]};
  const html=renderToStaticMarkup(createElement(DemographicAnalytics,{state:'COMPLETED',countRate:100,statistics}));
  expect(html).toContain('demographic-lock');expect(html).not.toContain('TEST_PRIVATE_GROUP');expect(html).not.toContain('73.12');
  const before=renderToStaticMarkup(createElement(DemographicAnalytics,{state:'RUNNING',countRate:99,statistics:{...statistics,evidence:ready}}));
  expect(before).not.toContain('TEST_PRIVATE_GROUP');
 });
 it('renders only validated presentation data after all gates, rejects invalid numbers',()=>{
  const statistics={evidence:ready,sourceUrl:'https://example.org/test-only',basis:'TEST ONLY',groups:[{label:'TEST_GROUP',turnoutPct:73.12}]};
  expect(renderToStaticMarkup(createElement(DemographicAnalytics,{state:'COMPLETED',countRate:100,statistics}))).toContain('demographic-chart');
  statistics.groups[0].turnoutPct=NaN;
  expect(renderToStaticMarkup(createElement(DemographicAnalytics,{state:'COMPLETED',countRate:100,statistics}))).toContain('demographic-lock');
 });
});
