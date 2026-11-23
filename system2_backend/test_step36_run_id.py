"""Run lifecycle regression; only owned loopback child servers are stopped."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from uuid import UUID, uuid4

import httpx
import websockets

from simulation_receiver import SimulationReceiver
from test_step25 import event
from test_step28 import ack, heartbeat


ROOT = Path(__file__).resolve().parent.parent


class RunIdTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.processes = []
        self.client = httpx.AsyncClient(timeout=3)

    async def asyncTearDown(self):
        await self.client.aclose()
        for process in reversed(self.processes):
            await self.stop(process)

    async def stop(self, process):
        if process.poll() is None:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, 5)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait, 5)

    async def boot(self, folder='system1_backend', port=None, extra=None):
        if port is None:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
        process = subprocess.Popen(
            [sys.executable, '-B', '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', str(port)],
            cwd=ROOT / folder,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', **(extra or {})},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.processes.append(process)
        async with asyncio.timeout(15):
            while True:
                self.assertIsNone(process.poll(), f'{folder} exited before ready')
                try:
                    response = await self.client.get(f'http://127.0.0.1:{port}/api/v0.1/health')
                    if response.status_code == 200:
                        return process, port
                except httpx.ConnectError:
                    pass
                await asyncio.sleep(.03)

    async def status(self, port):
        response = await self.client.get(f'http://127.0.0.1:{port}/api/v0.1/simulation/status')
        self.assertEqual(response.status_code, 200)
        return response.json()

    async def wait_status(self, port, predicate):
        async with asyncio.timeout(15):
            while True:
                state = await self.status(port)
                if predicate(state):
                    return state
                await asyncio.sleep(.03)

    def ws_url(self, port):
        return f'ws://127.0.0.1:{port}/ws/v0.1/simulation?client_role=system2'

    def assert_run(self, run):
        self.assertRegex(run, r'^MOCK_RUN_[0-9a-f]{32}$')
        self.assertEqual(UUID(hex=run.removeprefix('MOCK_RUN_')).version, 4)

    async def post(self, port, action, body):
        response = await self.client.post(f'http://127.0.0.1:{port}/api/v0.1/simulation/{action}', json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_start_stop_resume_reset_retry_reconnect_and_old_connection_ack(self):
        _, port = await self.boot()
        async with websockets.connect(self.ws_url(port)) as ws:
            first = json.loads(await ws.recv())
        run = first['run_id']
        self.assert_run(run)
        self.assertEqual(first['snapshot_id'], f'{run}_S1')
        start = dict(expected_run_id=run, election_id='0020260603', election_type='GOVERNOR',
                     scenario_id='MOCK_SEOUL_10000_V01', data_mode='MOCK', simulated=True)
        started = await self.post(port, 'start', dict(start, request_id=uuid4().hex))
        stopped = await self.post(port, 'stop', dict(expected_run_id=run, request_id=uuid4().hex))
        resumed = await self.post(port, 'start', dict(start, request_id=uuid4().hex))
        self.assertEqual([s['run_id'] for s in (started, stopped, resumed)], [run] * 3)
        self.assertEqual([s['state'] for s in (started, stopped, resumed)], ['RUNNING', 'PAUSED', 'RUNNING'])
        self.assertLess(started['seq'], stopped['seq'])
        self.assertLess(stopped['seq'], resumed['seq'])
        reset_request = dict(expected_run_id=run, request_id=uuid4().hex)
        reset = await self.post(port, 'reset', reset_request)
        repeated = await self.post(port, 'reset', reset_request)
        self.assertEqual(reset, repeated)
        self.assert_run(reset['run_id'])
        self.assertNotEqual(reset['run_id'], run)
        state = await self.status(port)
        self.assertEqual((state['run_id'], state['state'], state['seq']), (reset['run_id'], 'IDLE', 1))
        self.assertEqual(state['snapshot']['regions'][0]['counted_votes'], 0)
        async with websockets.connect(self.ws_url(port)) as ws:
            reset_snapshot = json.loads(await ws.recv())
        async with websockets.connect(self.ws_url(port)) as ws:
            reconnected = json.loads(await ws.recv())
            self.assertEqual(reconnected['run_id'], reset['run_id'])
            self.assertEqual(reconnected['snapshot_id'], f"{reset['run_id']}_S1")
            self.assertEqual((reconnected['seq'], reconnected['sync_cursor_seq']), (1, 1))
            self.assertNotEqual(reset_snapshot['connection_id'], reconnected['connection_id'])
            # Use current data and run so rejection specifically exercises the old connection.
            await ws.send(json.dumps(ack(reconnected, connection=reset_snapshot['connection_id'])))
            rejected = await self.wait_status(port, lambda s: s['system2']['rejected_feedback'] == 1)
            self.assertIsNone(rejected['system2']['last_acked_seq'])
            # Then use the current connection with a previous run.
            await ws.send(json.dumps(ack(reconnected, connection=reconnected['connection_id'], run_id=run)))
            rejected = await self.wait_status(port, lambda s: s['system2']['rejected_feedback'] == 2)
            self.assertIsNone(rejected['system2']['last_acked_seq'])
            await ws.send(json.dumps(ack(reconnected, connection=reconnected['connection_id'])))
            await ws.send(json.dumps(heartbeat(reset['run_id'], connection=reconnected['connection_id'])))
            synced = await self.wait_status(port, lambda s: s['system2']['receiver_state'] == 'SYNCED')
            self.assertEqual(synced['system2']['last_acked_seq'], 1)

    async def test_live_system2_accepts_system1_process_restart(self):
        first_process, p1 = await self.boot()
        receiver_process, p2 = await self.boot('system2_backend', extra={'SYSTEM1_WS_URL': self.ws_url(p1)})
        old = await self.wait_status(p2, lambda s: s['synchronized'] and s['ack_sent_count'] >= 1)
        # Retire the startup run before restarting, reproducing the STEP 35 failure path.
        reset = await self.post(p1, 'reset', dict(expected_run_id=old['run_id'], request_id=uuid4().hex))
        before = await self.wait_status(p2, lambda s: s['run_id'] == reset['run_id'] and s['last_acked_seq'] == 1)
        await self.stop(first_process)
        second_process, _ = await self.boot(port=p1)
        new = await self.status(p1)
        self.assert_run(old['run_id'])
        self.assert_run(new['run_id'])
        self.assertNotIn(new['run_id'], {old['run_id'], reset['run_id']})
        self.assertNotEqual(old['snapshot_id'], new['snapshot']['snapshot_id'])
        self.assertNotEqual(first_process.pid, second_process.pid)
        after = await self.wait_status(p2, lambda s: s['run_id'] == new['run_id']
                                       and s['synchronized'] and s['last_acked_seq'] == 1)
        self.assertIsNone(receiver_process.poll())
        self.assertEqual(before['receiver_instance_id'], after['receiver_instance_id'])
        self.assertGreater(after['connection_count'], before['connection_count'])
        self.assertEqual(after['snapshot_id'], new['snapshot']['snapshot_id'])
        self.assertEqual(after['storage_state'], 'MEMORY_APPLIED')
        self.assertEqual(after['validation_state'], 'PASS')
        sender = await self.wait_status(p1, lambda s: s['system2'] is not None
                                        and s['system2']['receiver_state'] == 'SYNCED')
        self.assertEqual(sender['system2']['run_id'], after['run_id'])

    async def test_previous_run_events_are_rejected_without_rewinding(self):
        receiver = SimulationReceiver()
        a, b = f'MOCK_RUN_{uuid4().hex}', f'MOCK_RUN_{uuid4().hex}'
        self.assertTrue(receiver.apply(event(run=a)))
        self.assertTrue(receiver.apply(event(run=b)))
        self.assertIn(a, receiver.retired_runs)
        before = deepcopy(receiver.data['snapshot'])
        for kind in ('snapshot', 'update', 'status'):
            with self.subTest(kind=kind):
                self.assertFalse(receiver.apply(event(99, run=a, kind=kind)))
                self.assertEqual(receiver.data['run_id'], b)
                self.assertEqual(receiver.data['snapshot'], before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
