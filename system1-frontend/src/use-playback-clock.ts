import { useEffect, useRef, useState } from 'react';
import type { State } from './types';
/** UI playback stopwatch, never a Backend progress signal or a source of vote counts. */
export function usePlaybackClock(run: string, state: State, connected: boolean) {
  const clock = useRef({run, elapsed:0});
  const [value,setValue] = useState(0);
  useEffect(()=>{
    if (clock.current.run !== run) { clock.current={run,elapsed:0};setValue(0); }
    if (state !== 'RUNNING' || !connected) return;
    const start = performance.now();
    const base = clock.current.elapsed;
    const timer = setInterval(()=>setValue(base+performance.now()-start),100);
    return ()=>{clearInterval(timer);clock.current.elapsed=base+performance.now()-start;setValue(clock.current.elapsed);};
  },[run,state,connected]);
  return Math.floor(value/1000);
}
export function formatDuration(seconds: number) {
  return Math.floor(seconds/60).toString().padStart(2,'0')+':'+(seconds%60).toString().padStart(2,'0');
}
