import asyncio
from contextlib import suppress
from copy import deepcopy
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
from test_step25 import event
from test_step24 import until
from simulation_receiver import SimulationReceiver
from main import create_app
from receiver_tracking import ReceiverSession


def ack(frame, connection='CONN', **changes):
    result = dict(type='ack',receiver_id='SYSTEM2',receiver_instance_id='INSTANCE',
        connection_id=connection,run_id=frame['run_id'],acked_seq=frame['seq'],
        snapshot_id=frame['snapshot_id'],result='APPLIED',received_at=frame['event_time'],
        applied_at=frame['event_time'],data_mode='MOCK',simulated=True)
    result.update(changes)
    return result


def heartbeat(run='A', connection='CONN', **changes):
    result = dict(type='heartbeat',receiver_id='SYSTEM2',receiver_instance_id='INSTANCE',
                  connection_id=connection,run_id=run)
    result.update(changes)
    return result


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.s = ReceiverSession('CONN',clock=lambda:self.now)
        self.e = event()
        self.s.sent_event(self.e)

    def test_normal_ack_heartbeat_and_identity_not_authentication(self):
        self.assertEqual(self.s.view()['receiver_state'],'AWAITING_ACK')
        self.assertIsNone(self.s.view()['ack_lag_events'])
        self.assertTrue(self.s.receive(ack(self.e),'A'))
        self.assertNotEqual(self.s.view()['receiver_state'],'SYNCED')
        self.assertTrue(self.s.receive(heartbeat(),'A'))
        view = self.s.view()
        self.assertEqual(view['receiver_state'],'SYNCED')
        self.assertTrue(view['live_verified'])
        self.assertFalse(view['authenticated'])

    def test_lag_counts_data_versions_not_sequence_difference(self):
        self.s.receive(ack(self.e),'A')
        self.s.receive(heartbeat(),'A')
        self.s.sent_event(event(7,kind='update'))
        self.s.sent_event(event(11,kind='update'))
        self.assertEqual(self.s.view()['receiver_state'],'LAGGING')
        self.assertEqual(self.s.view()['ack_lag_events'],2)
        self.now=10
        self.assertEqual(self.s.view()['receiver_state'],'LAGGING')
        self.now=10.001
        self.assertEqual(self.s.view()['receiver_state'],'STALE')
        self.s.receive(ack(event(11)),'A')
        self.assertEqual(self.s.view()['receiver_state'],'SYNCED')

    def test_heartbeat_timeout_and_close(self):
        self.s.receive(ack(self.e),'A')
        self.s.receive(heartbeat(),'A')
        self.now=15
        self.assertEqual(self.s.view()['receiver_state'],'SYNCED')
        self.now=15.001
        self.assertEqual(self.s.view()['receiver_state'],'DISCONNECTED')
        self.assertFalse(self.s.view()['live_verified'])
        self.s.receive(heartbeat(),'A')
        self.assertEqual(self.s.view()['receiver_state'],'SYNCED')
        self.s.close()
        self.assertEqual(self.s.view()['transport'],'DISCONNECTED')
        self.assertFalse(self.s.receive(ack(self.e),'A'))

    def test_initial_ack_timeout(self):
        self.now=10.001
        self.assertEqual(self.s.view()['receiver_state'],'STALE')
        self.assertIsNone(self.s.view()['ack_lag_events'])

    def test_bad_ack_no_state_advancement(self):
        for bad in (None, [], {}, {'type': []}):
            self.assertFalse(self.s.receive(bad,'A'))
        for changes in [dict(run_id='OLD'),dict(connection_id='OLD'),dict(acked_seq=999),
                dict(acked_seq=True),dict(snapshot_id='UNKNOWN'),dict(result='FAIL'),
                dict(data_mode='REAL_FINAL'),dict(simulated=False),dict(applied_at='bad')]:
            with self.subTest(changes=changes):
                self.assertFalse(self.s.receive(ack(self.e,**changes),'A'))
                self.assertIsNone(self.s.last_acked_seq)
        self.s.receive(heartbeat(),'A')
        self.assertFalse(self.s.receive(ack(self.e,receiver_instance_id='OTHER'),'A'))
        self.assertFalse(self.s.receive(heartbeat(receiver_id='OTHER'),'A'))
        frontend = ReceiverSession('CONN',role='frontend')
        frontend.sent_event(self.e)
        self.assertFalse(frontend.receive(ack(self.e),'A'))

    def test_duplicate_reverse_and_previous_connection(self):
        self.s.sent_event(event(3,kind='update'))
        self.assertTrue(self.s.receive(ack(event(3)),'A'))
        before=self.s.last_ack_at
        self.assertFalse(self.s.receive(ack(event(3)),'A'))
        self.assertFalse(self.s.receive(ack(self.e),'A'))
        self.assertEqual(self.s.last_acked_seq,3)
        self.assertEqual(self.s.last_ack_at,before)
        replacement=ReceiverSession('NEW')
        replacement.sent_event(self.e)
        self.assertFalse(replacement.receive(ack(self.e),'A'))

    def test_reset_drops_ack_and_heartbeat_but_completed_does_not_fake_ack(self):
        self.s.receive(ack(self.e),'A')
        self.s.receive(heartbeat(),'A')
        self.s.reset('B')
        self.assertEqual(self.s.view()['receiver_state'],'AWAITING_ACK')
        self.assertIsNone(self.s.last_acked_seq)
        self.assertIsNone(self.s.last_heartbeat_at)
        self.assertFalse(self.s.receive(ack(self.e),'B'))
        self.s.sent_event(event(1,'B'))
        self.s.sent_event(event(2,'B','status',state='COMPLETED'))
        self.assertIsNone(self.s.last_acked_seq)
        self.assertEqual(self.s.last_sent_seq,1)


class ReceiverTests(unittest.IsolatedAsyncioTestCase):
    async def test_ack_only_after_memory_apply_and_data_seq(self):
        class Sink:
            def __init__(self): self.frames=[]
            async def send(self,text): self.frames.append(json.loads(text))
        sink=Sink()
        r=SimulationReceiver()
        r.data['connection_id']='CONN'
        self.assertFalse(await r.send_ack(sink,event(),applied=False))
        e=event(3,sync_cursor_seq=4)
        self.assertTrue(r.apply(e))
        self.assertTrue(await r.send_ack(sink,e,applied=True))
        self.assertEqual(sink.frames[0]['acked_seq'],3)
        self.assertEqual(r.data['seq'],4)
        status=event(5,kind='status')
        self.assertTrue(r.apply(status))
        self.assertFalse(await r.send_ack(sink,status,applied=True))
        bad=event(6,kind='update')
        bad['regions'][0]['valid_votes']=123
        self.assertFalse(r.apply(bad))
        self.assertFalse(await r.send_ack(sink,bad,applied=True))
        err=event(7,kind='error',state='ERROR',error={'code':'TEST'})
        self.assertFalse(r.apply(err))
        self.assertFalse(await r.send_ack(sink,err,applied=False))
        self.assertEqual(len(sink.frames),1)

    async def test_real_ws_invalid_data_no_applied_ack(self):
        frames=[]
        first_connection=asyncio.Event()
        async def handler(ws):
            if first_connection.is_set():
                await ws.wait_closed()
                return
            first_connection.set()
            await ws.send(json.dumps(event(connection_id='TEST_CONNECTION')))
            frames.append(json.loads(await ws.recv()))
            frames.append(json.loads(await ws.recv()))
            await ws.send(json.dumps(event(2,kind='status')))
            bad=event(3,kind='update')
            bad['regions'][0]['valid_votes']=999
            await ws.send(json.dumps(bad))
            with suppress(websockets.exceptions.ConnectionClosed):
                async for message in ws:
                    frames.append(json.loads(message))
        async with websockets.serve(handler,'127.0.0.1',0) as server:
            port=server.sockets[0].getsockname()[1]
            r=SimulationReceiver(f'ws://127.0.0.1:{port}',.01,.05)
            task=asyncio.create_task(r.run())
            try:
                await until(lambda:r.data['invalid_events']==1)
                self.assertEqual([f['acked_seq'] for f in frames if f['type']=='ack'],[1])
                self.assertEqual(r.data['snapshot']['seq'],1)
                self.assertFalse(r.data['synchronized'])
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError): await task


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_process_http_status_and_wire_ack_rejections(self):
        def free_port():
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0))
                return sock.getsockname()[1]
        p1,p2=free_port(),free_port()
        root=Path(__file__).resolve().parent.parent
        processes=[]
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
        url=f'ws://127.0.0.1:{p1}/ws/v0.1/simulation?client_role=system2'
        evidence={}
        try:
            for folder,port,extra in [('system1_backend',p1,{}),('system2_backend',p2,{'SYSTEM1_WS_URL':url})]:
                processes.append(subprocess.Popen([sys.executable,'-m','uvicorn','main:app','--host','127.0.0.1','--port',str(port)],
                    cwd=root/folder,env={**env,**extra},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
            async with httpx.AsyncClient() as c:
                async def s1(): return (await c.get(f'http://127.0.0.1:{p1}/api/v0.1/simulation/status')).json()
                async with asyncio.timeout(12):
                    while True:
                        try:
                            one=await s1()
                            two=(await c.get(f'http://127.0.0.1:{p2}/api/v0.1/simulation/status')).json()
                            if one['system2'] and one['system2']['receiver_state']=='SYNCED' and two['ack_sent_count']>=1:
                                break
                        except httpx.ConnectError: pass
                        await asyncio.sleep(.05)
                self.assertEqual(one['system2']['connection_id'],two['connection_id'])
                self.assertEqual(one['system2']['last_acked_seq'],two['last_applied_seq'])
                self.assertEqual(one['system2']['snapshot_id'],two['snapshot_id'])
                self.assertEqual(two['data_mode'],'MOCK')
                self.assertTrue(two['simulated'])
                self.assertFalse(two['official_data'])
                self.assertFalse(two['authenticated'])
                evidence['two_process_system1']=one
                evidence['two_process_system2']=two
                old_connection=two['connection_id']
                processes[1].terminate()
                await asyncio.to_thread(processes[1].wait,5)
                async with asyncio.timeout(5):
                    while (await s1())['system2']['receiver_state']!='DISCONNECTED':
                        await asyncio.sleep(.02)
                evidence['closed']=await s1()
                async with websockets.connect(url) as ws:
                    snapshot=json.loads(await ws.recv())
                    connection=snapshot['connection_id']
                    self.assertNotEqual(connection,old_connection)
                    self.assertEqual((await s1())['system2']['receiver_state'],'AWAITING_ACK')
                    await ws.send(json.dumps(ack(snapshot,connection=old_connection)))
                    await ws.send(json.dumps(ack(snapshot,connection=connection,run_id='OTHER_RUN')))
                    await ws.send(json.dumps(ack(snapshot,connection=connection,acked_seq=9999)))
                    async with asyncio.timeout(5):
                        while (await s1())['system2']['rejected_feedback']<3:
                            await asyncio.sleep(.02)
                    self.assertIsNone((await s1())['system2']['last_acked_seq'])
                    good=ack(snapshot,connection=connection)
                    await ws.send(json.dumps(good))
                    await ws.send(json.dumps(heartbeat(snapshot['run_id'],connection=connection)))
                    async with asyncio.timeout(5):
                        while (await s1())['system2']['receiver_state']!='SYNCED':
                            await asyncio.sleep(.02)
                    await ws.send(json.dumps(good))
                    async with asyncio.timeout(5):
                        while (await s1())['system2']['ignored_acks']<1:
                            await asyncio.sleep(.02)
                    evidence['wire_rejections_and_duplicate']=await s1()
                async with websockets.connect(url) as ws:
                    replacement=json.loads(await ws.recv())
                    await ws.send(json.dumps(good))
                    async with asyncio.timeout(5):
                        while (await s1())['system2']['rejected_feedback']<1:
                            await asyncio.sleep(.02)
                    self.assertIsNone((await s1())['system2']['last_acked_seq'])
                    evidence['previous_connection_blocked']=await s1()
            (root/'system2_backend/STEP28_two_process_payloads.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    await asyncio.to_thread(process.wait,5)

    async def test_real_systems_ack_heartbeat_stop_reset_reconnect_complete(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        root=Path(__file__).resolve().parent.parent
        process=subprocess.Popen([sys.executable,'-m','uvicorn','main:app','--host','127.0.0.1','--port',str(port)],
            cwd=root/'system1_backend',env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        r=SimulationReceiver(f'ws://127.0.0.1:{port}/ws/v0.1/simulation?client_role=system2',.01,.05)
        app=create_app(r)
        evidence={}
        try:
            base=f'http://127.0.0.1:{port}/api/v0.1'
            async with httpx.AsyncClient() as c:
                async with asyncio.timeout(10):
                    while True:
                        try:
                            if (await c.get(base+'/health')).status_code==200: break
                        except httpx.ConnectError: pass
                        await asyncio.sleep(.05)
                async def status(): return (await c.get(base+'/simulation/status')).json()
                async def synced():
                    async with asyncio.timeout(8):
                        while True:
                            d=await status()
                            if d['system2'] and d['system2']['receiver_state']=='SYNCED': return d
                            await asyncio.sleep(.02)
                async with app.router.lifespan_context(app):
                    await until(lambda:r.data['synchronized'])
                    evidence['initial']=await synced()
                    self.assertFalse(evidence['initial']['system2']['authenticated'])
                    self.assertEqual(evidence['initial']['system2']['last_acked_seq'],r.data['snapshot']['seq'])
                    run=r.data['run_id']
                    async def start():
                        body=dict(request_id=uuid4().hex,expected_run_id=run,election_id='0020260603',election_type='GOVERNOR',scenario_id='MOCK_SEOUL_10000_V01',data_mode='MOCK',simulated=True)
                        self.assertEqual((await c.post(base+'/simulation/start',json=body)).status_code,200)
                    await start()
                    await until(lambda:r.data['snapshot']['regions'][0]['counted_votes']>0)
                    self.assertEqual((await c.post(base+'/simulation/stop',json=dict(request_id=uuid4().hex,expected_run_id=run))).status_code,200)
                    await until(lambda:r.data['state']=='PAUSED')
                    stopped=await synced()
                    evidence['stopped']=stopped
                    self.assertLess(stopped['system2']['last_acked_seq'],stopped['seq'])
                    hb=stopped['system2']['last_heartbeat_at']
                    async with asyncio.timeout(7):
                        while (await status())['system2']['last_heartbeat_at']==hb:
                            await asyncio.sleep(.05)
                    evidence['paused_heartbeat']=await synced()
                    old_connection=r.data['connection_id']
                await until(lambda:r.data['connection']=='DISCONNECTED')
                async with asyncio.timeout(5):
                    while (await status())['system2']['receiver_state']!='DISCONNECTED':
                        await asyncio.sleep(.02)
                async with app.router.lifespan_context(app):
                    await until(lambda:r.data['synchronized'])
                    evidence['reconnected']=await synced()
                    self.assertNotEqual(r.data['connection_id'],old_connection)
                    self.assertEqual(evidence['reconnected']['system2']['last_acked_seq'],r.data['snapshot']['seq'])
                    reset=await c.post(base+'/simulation/reset',json=dict(request_id=uuid4().hex,expected_run_id=run))
                    self.assertEqual(reset.status_code,200)
                    run=reset.json()['run_id']
                    await until(lambda:r.data['run_id']==run)
                    evidence['reset']=await synced()
                    self.assertEqual(evidence['reset']['system2']['last_acked_seq'],1)
                    self.assertEqual(evidence['reset']['system2']['run_id'],run)
                    await start()
                    await until(lambda:r.data['state']=='COMPLETED',timeout=25)
                    evidence['completed']=await synced()
                    final=evidence['completed']
                    self.assertEqual(final['system2']['last_acked_seq'],final['snapshot']['seq'])
                    self.assertLess(final['system2']['last_acked_seq'],final['seq'])
                    self.assertEqual(r.data['invalid_events'],0)
                    self.assertEqual(r.data['snapshot']['regions'][0]['counted_votes'],10000)
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as api:
                        local=(await api.get('/api/v0.1/simulation/status')).json()
                        self.assertEqual(local['storage_state'],'MEMORY_APPLIED')
                        self.assertFalse(local['authenticated'])
                        self.assertEqual(local['ack_delivery_status'],'SENT_UNCONFIRMED')
                        self.assertTrue(local['publication_blocked'])
                        evidence['system2']=local
            (root/'system2_backend/STEP28_payloads.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
        finally:
            process.terminate()
            await asyncio.to_thread(process.wait,5)


if __name__=='__main__': unittest.main(verbosity=2)
