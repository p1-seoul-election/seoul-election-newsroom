import json
import unittest

from simulation_receiver import SimulationReceiver
from simulation_storage import MemorySimulationStore
from test_step25 import event


class RecordingStore(MemorySimulationStore):
    def __init__(self):
        self.calls = []

    def __bool__(self):
        return False

    def apply_validated(self, event, **context):
        self.calls.append((event["run_id"], event["seq"], context["cursor"]))
        super().apply_validated(event, **context)


class StorageTests(unittest.TestCase):
    def test_default_and_injected_store_preserve_state_shape(self):
        default = SimulationReceiver()
        store = RecordingStore()
        injected = SimulationReceiver(storage=store)
        self.assertIsInstance(default.storage, MemorySimulationStore)
        self.assertIs(injected.storage, store)
        self.assertEqual(default.view(), injected.view())
        self.assertTrue(injected.apply(event()))
        self.assertEqual(store.calls, [('A', 1, 1)])

    def test_invalid_duplicate_and_gap_never_reach_store(self):
        store = RecordingStore()
        receiver = SimulationReceiver(storage=store)
        self.assertFalse(receiver.apply(event(data_mode='REAL_FINAL')))
        self.assertEqual(store.calls, [])
        self.assertTrue(receiver.apply(event()))
        before = receiver.view()['snapshot']
        self.assertFalse(receiver.apply(event()))
        self.assertFalse(receiver.apply(event(3, kind='update')))
        self.assertEqual(store.calls, [('A', 1, 1)])
        self.assertEqual(receiver.view()['snapshot'], before)

    def test_snapshot_update_catalog_and_view_are_isolated(self):
        receiver = SimulationReceiver()
        first = event()
        self.assertTrue(receiver.apply(first))
        first['catalog']['candidates'][0]['candidate_name'] = 'changed input'
        expected = receiver.view()['snapshot']['catalog']
        update = event(2, kind='update')
        del update['catalog']
        self.assertTrue(receiver.apply(update))
        update['regions'][0]['target_ballots'] = -1
        view = receiver.view()
        self.assertEqual(view['snapshot']['catalog'], expected)
        self.assertGreater(view['snapshot']['regions'][0]['target_ballots'], 0)
        view['snapshot']['catalog']['candidates'].clear()
        self.assertEqual(receiver.view()['snapshot']['catalog'], expected)
        self.assertEqual(receiver.data['storage_state'], 'MEMORY_APPLIED')

    def test_status_preserves_data_version_and_application_time(self):
        receiver = SimulationReceiver()
        self.assertTrue(receiver.apply(event(3, sync_cursor_seq=4)))
        before = receiver.view()
        self.assertTrue(receiver.apply(event(5, kind='status', state='PAUSED')))
        after = receiver.view()
        self.assertEqual(after['seq'], 5)
        self.assertEqual(after['snapshot']['seq'], 3)
        self.assertEqual(after['snapshot']['regions'], before['snapshot']['regions'])
        self.assertEqual(after['last_applied_at'], before['last_applied_at'])
        self.assertEqual(after['last_applied_seq'], 3)
        self.assertEqual(after['snapshot']['state'], 'PAUSED')

    def test_reset_retires_run_and_clears_ack_state(self):
        receiver = SimulationReceiver()
        self.assertTrue(receiver.apply(event()))
        receiver.data.update(last_acked_seq=1, last_ack_sent_at='previous')
        self.assertTrue(receiver.apply(event(1, run='B')))
        self.assertIn('A', receiver.retired_runs)
        self.assertIsNone(receiver.data['last_acked_seq'])
        self.assertIsNone(receiver.data['last_ack_sent_at'])
        before = receiver.view()['snapshot']
        self.assertFalse(receiver.apply(event(99, run='A')))
        self.assertEqual(receiver.view()['snapshot'], before)

    def test_reconnect_cursor_advance_does_not_change_data_version(self):
        store = RecordingStore()
        receiver = SimulationReceiver(storage=store)
        self.assertTrue(receiver.apply(event(3)))
        reconnect = event(3, sync_cursor_seq=7, state='PAUSED')
        self.assertTrue(receiver.apply(reconnect, initial=True))
        self.assertEqual(receiver.data['seq'], 7)
        self.assertEqual(receiver.data['last_applied_seq'], 3)
        self.assertFalse(receiver.apply(reconnect, initial=True))
        self.assertTrue(receiver.same_snapshot(reconnect))
        self.assertEqual(store.calls, [('A', 3, 3), ('A', 3, 7)])


class AckBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_ack_observes_applied_store_and_current_connection(self):
        store = RecordingStore()
        receiver = SimulationReceiver(storage=store)
        receiver.data['connection_id'] = 'CURRENT'
        frame = event(3, sync_cursor_seq=4)
        frames = []
        testcase = self

        class Socket:
            async def send(self, raw):
                testcase.assertEqual(store.calls, [('A', 3, 4)])
                testcase.assertEqual(receiver.data['storage_state'], 'MEMORY_APPLIED')
                testcase.assertEqual(receiver.data['last_applied_seq'], 3)
                frames.append(json.loads(raw))

        ws = Socket()
        self.assertFalse(await receiver.send_ack(ws, frame, applied=True))
        self.assertTrue(receiver.apply(frame, initial=True))
        self.assertTrue(await receiver.send_ack(ws, frame, applied=True))
        self.assertEqual(frames[0]['result'], 'APPLIED')
        self.assertEqual(frames[0]['acked_seq'], 3)
        self.assertEqual(frames[0]['connection_id'], 'CURRENT')
        self.assertFalse(receiver.apply(frame, initial=True))
        self.assertTrue(receiver.same_snapshot(frame))
        receiver.data['connection_id'] = 'RECONNECTED'
        self.assertTrue(await receiver.send_ack(ws, frame, applied=True))
        self.assertEqual(frames[1]['connection_id'], 'RECONNECTED')
        self.assertEqual(len(store.calls), 1)

    async def test_status_and_invalid_event_do_not_gain_ack(self):
        receiver = SimulationReceiver()
        receiver.data['connection_id'] = 'CURRENT'
        frames = []

        class Socket:
            async def send(self, raw):
                frames.append(raw)

        self.assertTrue(receiver.apply(event()))
        status = event(2, kind='status', state='PAUSED')
        self.assertTrue(receiver.apply(status))
        self.assertFalse(await receiver.send_ack(Socket(), status, applied=True))
        bad = event(3, kind='update', official_data=True)
        self.assertFalse(receiver.apply(bad))
        self.assertFalse(await receiver.send_ack(Socket(), bad, applied=True))
        self.assertEqual(frames, [])


if __name__ == '__main__':
    unittest.main()
