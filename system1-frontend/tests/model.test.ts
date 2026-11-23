import { describe, it, expect, vi, afterEach } from 'vitest';
import { initialView, normal, copy, receive, MockAdapter } from '../src/mock-adapter';
import { validateFrame } from '../src/validation';
import fixture from '../src/fixtures/mock-v0.1.json';
import type { Frame } from '../src/types';
afterEach(()=>vi.useRealTimers());
describe('Contract data integrity',()=>{
 it('accepts original normal/reset fixtures and preserves source IDs',()=>{
  for(const f of normal) expect(validateFrame(f)).toBeNull();
  expect(validateFrame(fixture.scenarios.reset.frame)).toBeNull();
  expect(normal[2].regions![0].candidate_votes.map(c=>c.candidate_id.slice(-3))).toEqual(['C01','C02','C04','C05','C07']);
 });
 it('uses replacement values and correct denominators; rejects duplicate and backward sequences',()=>{
  let v = receive(initialView(),normal[1]); v = receive(v,normal[2]);
  expect(v.snapshot.regions![0].counted_votes).toBe(2020);
  expect(v.snapshot.regions![0].count_rate_pct).toBe(20.2);
  expect(v.snapshot.regions![0].candidate_votes[0].vote_share_pct).toBe(50);
  const dup = receive(v,normal[2]);
  expect(dup.snapshot).toBe(v.snapshot); expect(dup.logs.at(-1)?.outcome).toBe('IGNORED');
 });
 it('rejects malformed numbers, unknown/duplicate IDs, missing candidates, totals and decreases',()=>{
  const mutations: ((f:Frame)=>void)[] = [
   f=>{f.regions![0].counted_votes=-1;}, f=>{f.regions![0].counted_votes=NaN;},
   f=>{(f.regions![0] as unknown as Record<string,unknown>).counted_votes='2020';},
   f=>{f.regions![0].candidate_votes[0].candidate_id='C03';},
   f=>{f.regions![0].candidate_votes[1].candidate_id=f.regions![0].candidate_votes[0].candidate_id;},
   f=>{f.regions![0].candidate_votes.pop();},
   f=>{f.regions![0].counted_votes=2019;}, f=>{f.regions![0].count_rate_pct=50;},
   f=>{f.regions![0].candidate_votes[0].vote_share_pct=49;},
   f=>{f.regions![0].region_id='UNKNOWN';}, f=>{f.data_mode='REAL_FINAL';}
  ];
  mutations.forEach(m=>{const f=copy(normal[2]);m(f);expect(validateFrame(f)).not.toBeNull();});
  expect(validateFrame(normal[0],normal[2])).toBe('CUMULATIVE_DECREASE');
 });
 it('keeps null share at zero and preserves last good snapshot on error',()=>{
  expect(normal[0].regions![0].candidate_votes.every(c=>c.vote_share_pct === null)).toBe(true);
  let v=receive(receive(initialView(),normal[1]),normal[2]);
  const bad=copy(fixture.scenarios.error.invalid_incoming_update) as Frame;bad.seq=4;
  const next=receive(v,bad);expect(next.snapshot).toBe(v.snapshot);expect(next.state).toBe('ERROR');expect(next.error).toContain('TOTAL_MISMATCH');
 });
 it('detects missing sequence and restores using sync_cursor_seq; rejects foreign run update',()=>{
  let v=receive(initialView(),normal[2]);expect(v.error).toContain('SEQ_GAP');
  const snapshot={...copy(normal[2]),type:'snapshot',sync_cursor_seq:4} as Frame;
  v=receive(v,snapshot,true);expect(v.cursor).toBe(4);expect(v.error).toBeNull();
  const foreign=copy(normal[2]);foreign.run_id='OTHER';foreign.seq=5;
  expect(receive(v,foreign).error).toContain('RUN_MISMATCH');
 });
});
describe('Working mock commands',()=>{
 it('stops, resumes same run and resets to a unique zero run while retaining audit',async()=>{
  vi.useFakeTimers(); const a=new MockAdapter();
  const start=a.command('start');await vi.advanceTimersByTimeAsync(120);await start;
  await vi.advanceTimersByTimeAsync(1400);expect(a.getSnapshot().snapshot.regions![0].counted_votes).toBe(2020);
  const run=a.getSnapshot().run;
  const stop=a.command('stop');await vi.advanceTimersByTimeAsync(120);await stop;
  await vi.advanceTimersByTimeAsync(10000);expect(a.getSnapshot().state).toBe('PAUSED');expect(a.getSnapshot().run).toBe(run);
  const resume=a.command('start');await vi.advanceTimersByTimeAsync(120);await resume;expect(a.getSnapshot().run).toBe(run);
  const reset=a.command('reset');await vi.advanceTimersByTimeAsync(120);await reset;
  expect(a.getSnapshot().run).not.toBe(run);expect(a.getSnapshot().state).toBe('IDLE');expect(a.getSnapshot().snapshot.regions![0].counted_votes).toBe(0);expect(a.getSnapshot().receiver.receiver_state).toBe('AWAITING_ACK');expect(a.getSnapshot().logs.some(l=>l.frame.run_id===run)).toBe(true);a.dispose();
 });
 it.each(['invalid','receiver-disconnect','ws-disconnect','ack-wait','lagging','stale','normal'] as const)('runs %s scenario without claiming live verification',async(s)=>{
  vi.useFakeTimers();const a=new MockAdapter();a.setScenario(s);
  const p=a.command('start');await vi.advanceTimersByTimeAsync(120);await p;await vi.advanceTimersByTimeAsync(2800);
  expect(a.getSnapshot().snapshot.regions![0].counted_votes).toBe(2020);
  expect(a.getSnapshot().receiver.live_verified).toBe(false);
  if(s==='invalid') expect(a.getSnapshot().error).toContain('TOTAL_MISMATCH');
  if(s==='receiver-disconnect') {expect(a.getSnapshot().receiver.transport).toBe('DISCONNECTED');expect(a.getSnapshot().state).toBe('ERROR');}
  if(s==='ws-disconnect') {expect(a.getSnapshot().transport).toBe('DISCONNECTED');a.reconnect();expect(a.getSnapshot().transport).toBe('CONNECTED');}
  if(s==='normal') expect(a.getSnapshot().receiver.receiver_state).toBe('SYNCED');
  if(s==='lagging') expect(a.getSnapshot().receiver.ack_lag_events).toBe(1);
  if(s==='stale') expect(a.getSnapshot().receiver.receiver_state).toBe('STALE');
  a.dispose();
 });
});
