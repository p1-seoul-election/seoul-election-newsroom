import sys
import copy
import importlib.util
from pathlib import Path
import unittest

from simulation_receiver import SimulationReceiver
from event_validation import validate

sys.path.append(str(Path(__file__).resolve().parent.parent / "system1_backend"))
spec = importlib.util.spec_from_file_location('provider_step25', Path(__file__).resolve().parent.parent / 'system1_backend' / 'main.py')
provider = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider)


def event(seq=1, run='A', kind='snapshot', **extra):
    value = provider.create_initial_snapshot(run)
    value.update(seq=seq, sync_cursor_seq=seq, type=kind, snapshot_id=f'{run}_S{seq}')
    if kind == 'status':
        for key in ('regions', 'catalog', 'scope_region_ids', 'snapshot_id'):
            value.pop(key)
        value['reason'] = 'TEST'
    value.update(extra)
    return value


class ValidationTests(unittest.TestCase):
    def test_valid_nonzero_invalid_ballots_and_review_gate(self):
        e = event()
        r = e['regions'][0]
        r.update(counted_votes=2020, valid_votes=2000, invalid_votes=20, count_rate_pct=20.2)
        for c, votes, share in zip(r['candidate_votes'], [1000,900,40,30,30], [50,45,2,1.5,1.5]):
            c.update(votes=votes, vote_share_pct=share)
        receiver = SimulationReceiver()
        self.assertTrue(receiver.apply(e))
        self.assertEqual(receiver.data['validation_state'], 'PASS')
        self.assertEqual(receiver.data['verification_state'], 'REVIEW_REQUIRED')
        self.assertTrue(receiver.data['approval_blocked'])
        self.assertTrue(receiver.data['publication_blocked'])
        self.assertFalse(receiver.data['official_data'])

    def test_bad_fields_atomic_preservation(self):
        mutations = [
            lambda e: e.update(seq=True), lambda e: e.update(run_id=''),
            lambda e: e.update(election_id=20260603), lambda e: e.update(contract_version='2'),
            lambda e: e.update(data_mode='REAL_FINAL', simulated=False),
            lambda e: e.update(official_data=True), lambda e: e.pop('reference'),
            lambda e: e.update(regions=[]), lambda e: e.update(scope_region_ids=['SEOUL_D01']),
            lambda e: e['regions'][0].update(valid_votes=1),
            lambda e: e['regions'][0].update(invalid_votes=1),
            lambda e: e['regions'][0].update(counted_votes=10001),
            lambda e: e['regions'][0].update(count_rate_pct=float('nan')),
            lambda e: e['regions'][0].update(target_ballots=0),
            lambda e: e['regions'][0]['candidate_votes'][0].update(votes=-1),
            lambda e: e['regions'][0]['candidate_votes'][0].update(votes=True),
            lambda e: e['regions'][0]['candidate_votes'][0].update(votes='0'),
            lambda e: e['regions'][0]['candidate_votes'][0].update(candidate_id='0020260603_SEOUL_C03'),
            lambda e: e['regions'][0]['candidate_votes'][0].update(candidate_id='0020260603_SEOUL_C02'),
            lambda e: e['regions'][0]['candidate_votes'].pop(),
            lambda e: e['regions'][0]['candidate_votes'][0].update(vote_share_pct=0),
            lambda e: e['reference'].update(verification_status='FAIL'),
            lambda e: e.update(state='COMPLETED'),
            lambda e: e.update(event_time='2026-11-20'),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                receiver = Simulationplib = SimulationReceiver()
                self.assertTrue(receiver.apply(event()))
                before = receiver.view()
                bad = event(2, kind='update')
                mutate(bad)
                self.assertFalse(receiver.apply(bad))
                for key in ('snapshot','run_id','seq','state','last_event','received_at'):
                    self.assertEqual(receiver.data[key], before[key])
                self.assertEqual(receiver.data['validation_state'], 'FAIL')
                self.assertTrue(receiver.data['publication_blocked'])

    def test_sequence_gap_and_snapshot_recovery(self):
        r = SimulationReceiver()
        self.assertTrue(r.apply(event()))
        self.assertFalse(r.apply(event(3, kind='update')))
        self.assertFalse(r.apply(event(2, kind='update')))
        self.assertTrue(r.apply(event(4)))
        self.assertTrue(r.apply(event(5, kind='update')))
        self.assertFalse(r.apply(event(4)))
        self.assertTrue(r.apply(event(1, 'B')))
        self.assertFalse(r.apply(event(100, 'A')))

    def test_reconnect_same_seq_tampering(self):
        r = SimulationReceiver()
        r.apply(event())
        self.assertTrue(r.same_snapshot(event()))
        bad = event()
        bad['regions'][0]['candidate_votes'][0]['vote_share_pct'] = 0
        self.assertFalse(r.same_snapshot(bad))
        bad = event()
        bad['reference']['dataset_version'] = 'changed'
        self.assertFalse(r.same_snapshot(bad))

    def test_candidate_decrease_and_target_change(self):
        r = SimulationReceiver()
        first = provider.calculate_next_mock_snapshot(event())
        self.assertTrue(r.apply(first))
        bad = copy.deepcopy(first)
        bad.update(seq=2, type='update')
        bad['regions'][0]['candidate_votes'][0]['votes'] -= 1
        bad['regions'][0]['candidate_votes'][1]['votes'] += 1
        for c in bad['regions'][0]['candidate_votes']:
            c['vote_share_pct'] = c['votes']/5
        self.assertFalse(r.apply(bad))
        self.assertIn('CANDIDATE_DECREASE', r.data['validation_errors'])
        bad = event(3)
        bad['regions'][0].update(target_ballots=20000)
        self.assertFalse(r.apply(bad))

    def test_provider_contract_conflicts_are_rejected(self):
        r = SimulationReceiver()
        r.apply(event())
        bad_status = event(2, kind='status')
        bad_status.pop('contract_status')
        self.assertFalse(r.apply(bad_status))
        self.assertIn('CONTRACT_STATUS', r.data['validation_errors'])
        bad = event(2)
        region = bad['regions'][0]
        region.update(valid_votes=3,counted_votes=3,count_rate_pct=.03)
        for c,v in zip(region['candidate_votes'],[1,2,0,0,0]):
            c.update(votes=v,vote_share_pct=round(v/3*100,2))
        self.assertFalse(r.apply(bad))
        self.assertIn('VOTE_SHARE', r.data['validation_errors'])
        for c,v in zip(region['candidate_votes'],[33.333333,66.666667,0,0,0]):
            c['vote_share_pct']=v
        self.assertTrue(r.apply(bad))

    def test_error_event_preserves_snapshot(self):
        r = SimulationReceiver()
        r.apply(event())
        old = r.view()['snapshot']
        bad = event(2, kind='error', state='ERROR', error={'code':'TEST'})
        self.assertFalse(r.apply(bad))
        self.assertEqual(r.data['snapshot'],old)
        self.assertEqual(r.data['verification_state'],'FAIL')


import asyncio
import json
import socket
import subprocess
import sys
import os
import httpx
import websockets
from main import create_app
from test_step24 import until


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_websocket_reject_reconnect_and_preserve(self):
        connections = 0
        release = asyncio.Event()
        async def handler(ws):
            nonlocal connections
            connections += 1
            if connections == 1:
                await ws.send(json.dumps(event()))
                await ws.send('broken-json')
                await ws.wait_closed()
            else:
                await release.wait()
                await ws.send(json.dumps(event(3)))
                await ws.send(json.dumps(event(4, kind='update')))
                await ws.wait_closed()
        async with websockets.serve(handler, '127.0.0.1', 0) as server:
            port = server.sockets[0].getsockname()[1]
            r = SimulationReceiver(f'ws://127.0.0.1:{port}', .01, .05)
            app = create_app(r)
            async with app.router.lifespan_context(app):
                await until(lambda: connections >= 2)
                self.assertEqual(r.data['seq'], 1)
                self.assertEqual(r.data['validation_state'], 'FAIL')
                self.assertFalse(r.data['synchronized'])
                release.set()
                await until(lambda: r.data['seq'] == 4)
                self.assertTrue(r.data['synchronized'])
                self.assertTrue(r.data['publication_blocked'])
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as c:
                    self.assertEqual((await c.get('/api/v0.1/health')).status_code,200)
                    data = (await c.get('/api/v0.1/simulation/status')).json()
                    self.assertEqual(data['verification_state'],'REVIEW_REQUIRED')
            self.assertEqual(r.data['connection'],'DISCONNECTED')

    async def test_real_provider_transport_and_status_contract_acceptance(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            port = sock.getsockname()[1]
        process = subprocess.Popen([sys.executable,'-m','uvicorn','main:app','--host','127.0.0.1','--port',str(port)],
            cwd=Path(__file__).resolve().parent.parent/'system1_backend',
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}, stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            async with httpx.AsyncClient() as c:
                async def ready():
                    async with asyncio.timeout(10):
                        while True:
                            try:
                                if (await c.get(f'http://127.0.0.1:{port}/api/v0.1/health')).status_code == 200:
                                    return
                            except httpx.ConnectError:
                                pass
                            await asyncio.sleep(.05)
                await ready()
                async with websockets.connect(f'ws://127.0.0.1:{port}/ws/v0.1/simulation?client_role=system2') as ws:
                    first = json.loads(await ws.recv())
                    r = SimulationReceiver()
                    self.assertTrue(r.apply(first,initial=True))
                    from uuid import uuid4
                    body = dict(request_id=uuid4().hex,expected_run_id=first['run_id'],election_id='0020260603',election_type='GOVERNOR',scenario_id='MOCK_SEOUL_10000_V01',data_mode='MOCK',simulated=True)
                    url = f'http://127.0.0.1:{port}/api/v0.1/simulation/start'
                    start = await c.post(url,json=body)
                    self.assertEqual(start.status_code,200)
                    self.assertEqual((await c.post(url,json=body)).json(),start.json())
                    status = json.loads(await asyncio.wait_for(ws.recv(),5))
                    saved = r.view()['snapshot']
                    self.assertEqual(status['type'],'status')
                    self.assertTrue(r.apply(status))
                    self.assertEqual(r.data['snapshot']['regions'],saved['regions'])
                    self.assertEqual(r.data['snapshot']['seq'],saved['seq'])
                    update = json.loads(await asyncio.wait_for(ws.recv(),5))
                    self.assertEqual(update['type'],'update')
                    self.assertTrue(r.apply(update))
                    self.assertEqual(r.data['seq'],update['seq'])
                async with websockets.connect(f'ws://127.0.0.1:{port}/ws/v0.1/simulation?client_role=system2') as ws:
                    current = json.loads(await ws.recv())
                    self.assertTrue(r.apply(current,initial=True) or r.same_snapshot(current))
                    self.assertEqual(r.data['snapshot']['regions'],current['regions'])
        finally:
            process.terminate()
            await asyncio.to_thread(process.wait,5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
