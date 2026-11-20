import asyncio
from contextlib import suppress
from copy import deepcopy
from decimal import Decimal
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from uuid import uuid4

import httpx
import websockets
from simulation_receiver import SimulationReceiver
from event_validation import validate
from test_step25 import event, provider
from test_step24 import until


class ContractTests(unittest.TestCase):
    def test_status_common_fields_and_reference_isolation(self):
        original = deepcopy(provider.simulation_state)
        try:
            provider.simulation_state.update(snapshot=event(), run_id='A', seq=2, state='RUNNING')
            provider.record_status_event('STARTED')
            status = provider.simulation_state['last_status_event']
            validate(status)
            self.assertEqual(status['reference'],provider.simulation_state['snapshot']['reference'])
            self.assertEqual(status['reference']['verification_status'],'REVIEW_REQUIRED')
            self.assertEqual(status['contract_status'],'PROPOSAL_UNIMPLEMENTED')
            for missing in ('contract_status','reference'):
                bad = deepcopy(status)
                bad.pop(missing)
                with self.assertRaises(ValueError):
                    validate(bad)
            status['reference']['source_ids'].clear()
            self.assertTrue(provider.simulation_state['snapshot']['reference']['source_ids'])
        finally:
            provider.simulation_state.clear()
            provider.simulation_state.update(original)

    def test_step26_fractional_count_rate_now_accepted(self):
        seed = event()
        seed['regions'][0]['target_ballots'] = 30000
        result = provider.calculate_next_mock_snapshot(seed)
        self.assertEqual(result['regions'][0]['count_rate_pct'],1.666667)
        validate(result)

    def test_step26_fractional_share_now_accepted(self):
        seed = event()
        r = seed['regions'][0]
        r.update(valid_votes=1,counted_votes=1,count_rate_pct=.01)
        for c, votes in zip(r['candidate_votes'],[1,0,0,0,0]):
            c.update(votes=votes,vote_share_pct=100 if votes else 0)
        result = provider.calculate_next_mock_snapshot(seed)
        self.assertEqual(result['regions'][0]['candidate_votes'][0]['vote_share_pct'],20.159681)
        validate(result)

    def test_half_up_tie_zero_and_json_numbers(self):
        self.assertEqual(provider.mock_percentage(1,200000000),.000001)
        self.assertEqual(provider.mock_percentage(0,3),0)
        self.assertIsNone(provider.mock_percentage(0,0))
        zero = event()
        validate(zero)
        self.assertTrue(all(c['vote_share_pct'] is None for c in zero['regions'][0]['candidate_votes']))
        for c in zero['regions'][0]['candidate_votes']:
            c['vote_share_pct'] = 0
        with self.assertRaisesRegex(ValueError,'VOTE_SHARE'):
            validate(zero)
        encoded = json.loads(json.dumps(provider.calculate_next_mock_snapshot(event())))
        validate(encoded)

    def test_contract_cursor_fresh_and_next_update(self):
        r = SimulationReceiver()
        self.assertTrue(r.apply(event(3,sync_cursor_seq=4),initial=True))
        self.assertEqual(r.data['seq'],4)
        self.assertEqual(r.data['snapshot']['seq'],3)
        self.assertTrue(r.apply(event(5,kind='update')))
        self.assertEqual(r.data['seq'],5)

    def test_reconnect_after_known_status_same_data(self):
        r = SimulationReceiver()
        self.assertTrue(r.apply(event(3)))
        self.assertTrue(r.apply(event(4,kind='status',state='PAUSED')))
        snapshot = event(3,sync_cursor_seq=4,state='PAUSED')
        before = r.view()
        self.assertFalse(r.apply(snapshot,initial=True))
        self.assertTrue(r.same_snapshot(snapshot))
        self.assertEqual(r.data['snapshot'],before['snapshot'])
        self.assertTrue(r.apply(event(5,kind='status',state='RUNNING')))

    def test_reconnect_cursor_advance_and_same_version_tamper(self):
        r = SimulationReceiver()
        self.assertTrue(r.apply(event(3)))
        self.assertTrue(r.apply(event(3,sync_cursor_seq=7,state='PAUSED'),initial=True))
        old = r.view()
        bad = event(3,sync_cursor_seq=8,state='PAUSED')
        bad['reference']['dataset_version'] = 'changed'
        self.assertFalse(r.apply(bad,initial=True))
        self.assertEqual(r.data['validation_errors'],['DATA_VERSION_CONFLICT'])
        self.assertEqual(r.data['snapshot'],old['snapshot'])

    def test_invalid_cursor_and_snapshot_preservation(self):
        for cursor in (None,True,'4',0,-1,2):
            with self.subTest(cursor=cursor):
                r = SimulationReceiver()
                r.apply(event())
                before = r.view()
                self.assertFalse(r.apply(event(3,sync_cursor_seq=cursor)))
                self.assertEqual(r.data['snapshot'],before['snapshot'])
                self.assertEqual(r.data['seq'],before['seq'])
                self.assertEqual(r.data['validation_errors'],['SYNC_CURSOR_SEQ'])
        bad = event()
        bad.pop('sync_cursor_seq')
        self.assertFalse(SimulationReceiver().apply(bad))

    def test_duplicate_reverse_gap_reset_and_gates(self):
        r = SimulationReceiver()
        r.apply(event(3,sync_cursor_seq=4))
        self.assertTrue(r.apply(event(5,kind='update')))
        old = r.view()
        for seq in (5,4):
            self.assertFalse(r.apply(event(seq,kind='update')))
            self.assertEqual(r.data['snapshot'],old['snapshot'])
            self.assertEqual(r.data['validation_state'],'PASS')
        self.assertFalse(r.apply(event(7,kind='update')))
        self.assertEqual(r.data['validation_errors'],['RESYNC_SNAPSHOT_REQUIRED'])
        self.assertTrue(r.apply(event(1,'B')))
        self.assertFalse(r.apply(event(99,'A')))
        self.assertTrue(r.data['approval_blocked'])
        self.assertTrue(r.data['publication_blocked'])
        self.assertFalse(r.data['official_data'])


class WireTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_reconnect_resume_and_reset_real_receiver(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            port = sock.getsockname()[1]
        root = Path(__file__).resolve().parent.parent
        process = subprocess.Popen([sys.executable,'-m','uvicorn','main:app','--host','127.0.0.1','--port',str(port)],
            cwd=root/'system1_backend',env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        task = None
        evidence = {}
        try:
            base = f'http://127.0.0.1:{port}/api/v0.1'
            async with httpx.AsyncClient() as c:
                async with asyncio.timeout(10):
                    while True:
                        try:
                            if (await c.get(base+'/health')).status_code == 200:
                                break
                        except httpx.ConnectError:
                            pass
                        await asyncio.sleep(.05)
                r = SimulationReceiver(f'ws://127.0.0.1:{port}/ws/v0.1/simulation?client_role=system2',.01,.05)
                task = asyncio.create_task(r.run())
                await until(lambda:r.data['synchronized'])
                run = r.data['run_id']
                async def start():
                    body = dict(request_id=uuid4().hex,expected_run_id=run,election_id='0020260603',election_type='GOVERNOR',scenario_id='MOCK_SEOUL_10000_V01',data_mode='MOCK',simulated=True)
                    self.assertEqual((await c.post(base+'/simulation/start',json=body)).status_code,200)
                await start()
                await until(lambda:r.data['snapshot']['regions'][0]['counted_votes']>0)
                self.assertEqual((await c.post(base+'/simulation/stop',json=dict(request_id=uuid4().hex,expected_run_id=run))).status_code,200)
                await until(lambda:r.data['state']=='PAUSED')
                stopped = r.view()
                self.assertGreater(stopped['seq'],stopped['snapshot']['seq'])
                evidence['stopped'] = stopped
                async with websockets.connect(r.url) as ws:
                    reconnect_wire = json.loads(await ws.recv())
                    validate(reconnect_wire)
                    self.assertEqual(reconnect_wire['seq'],stopped['snapshot']['seq'])
                    self.assertEqual(reconnect_wire['sync_cursor_seq'],stopped['seq'])
                    self.assertGreater(reconnect_wire['sync_cursor_seq'],reconnect_wire['seq'])
                    self.assertEqual(reconnect_wire['reference']['verification_status'],'REVIEW_REQUIRED')
                    evidence['wire_stopped_reconnect'] = reconnect_wire
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                task = asyncio.create_task(r.run())
                await until(lambda:r.data['synchronized'])
                self.assertEqual(r.data['connection_count'],2)
                self.assertEqual(r.data['seq'],stopped['seq'])
                self.assertEqual(r.data['snapshot']['seq'],stopped['snapshot']['seq'])
                self.assertEqual(r.data['snapshot']['regions'],stopped['snapshot']['regions'])
                evidence['reconnected'] = r.view()
                await start()
                await until(lambda:r.data['seq']>stopped['seq'])
                await until(lambda:r.data['snapshot']['regions'][0]['counted_votes']>stopped['snapshot']['regions'][0]['counted_votes'])
                reset = await c.post(base+'/simulation/reset',json=dict(request_id=uuid4().hex,expected_run_id=run))
                self.assertEqual(reset.status_code,200)
                await until(lambda:r.data['run_id']==reset.json()['run_id'])
                self.assertEqual(r.data['seq'],1)
                self.assertEqual(r.data['snapshot']['seq'],1)
                self.assertEqual(r.data['snapshot']['regions'][0]['counted_votes'],0)
                self.assertEqual(r.data['invalid_events'],0)
                self.assertTrue(r.data['publication_blocked'])
                evidence['reset'] = r.view()
                # Actual WS payload confirms source/data version and subscription cursor.
                async with websockets.connect(r.url) as ws:
                    wire = json.loads(await ws.recv())
                    validate(wire)
                    self.assertEqual(wire['seq'],1)
                    self.assertEqual(wire['sync_cursor_seq'],1)
                    evidence['wire_reset'] = wire
                (root/'system2_backend'/'STEP27_payloads.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
        finally:
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            process.terminate()
            await asyncio.to_thread(process.wait,5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
