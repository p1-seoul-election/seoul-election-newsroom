"""Per-WebSocket MOCK receiver feedback. Identity claims are NOT authentication."""
from datetime import datetime, timezone
import time


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class ReceiverSession:
    ACK_TIMEOUT = 10.0
    HEARTBEAT_TIMEOUT = 15.0

    def __init__(self, connection_id, role='system2', clock=time.monotonic):
        self.connection_id = connection_id
        self.role = role
        self.clock = clock
        self.opened = clock()
        self.connected = True
        self.receiver_id = self.instance_id = None
        self.rejected = self.duplicates = 0
        self.reset(None)

    def reset(self, run_id):
        self.run_id = run_id
        self.sent = {}
        self.pending = {}
        self.last_sent_seq = self.last_snapshot_id = None
        self.last_acked_seq = self.last_ack_at = None
        self.last_heartbeat_at = self.heartbeat_time = None
        self.run_started = self.clock()

    def sent_event(self, event):
        if event.get('type') not in {'snapshot', 'update'}:
            return
        if self.run_id != event['run_id']:
            self.reset(event['run_id'])
        key = (event['seq'], event['snapshot_id'])
        self.sent.setdefault(key, self.clock())
        if self.last_acked_seq is None or event['seq'] > self.last_acked_seq:
            self.pending.setdefault(key, self.sent[key])
        self.last_sent_seq = event['seq']
        self.last_snapshot_id = event['snapshot_id']

    @staticmethod
    def valid_stamp(value):
        try:
            return isinstance(value, str) and datetime.fromisoformat(value).utcoffset() is not None
        except ValueError:
            return False

    def receive(self, frame, current_run):
        def reject():
            self.rejected += 1
            return False
        if (not self.connected or self.role != 'system2' or not isinstance(frame, dict)
                or not isinstance(frame.get('type'), str)
                or frame.get('type') not in {'ack', 'heartbeat'}
                or frame.get('connection_id') != self.connection_id
                or frame.get('run_id') != current_run or self.run_id != current_run):
            return reject()
        receiver, instance = frame.get('receiver_id'), frame.get('receiver_instance_id')
        if (not isinstance(receiver, str) or not receiver.strip()
                or not isinstance(instance, str) or not instance.strip()
                or (self.receiver_id is not None and (receiver, instance) != (self.receiver_id, self.instance_id))):
            return reject()
        if frame['type'] == 'heartbeat':
            self.receiver_id, self.instance_id = receiver, instance
            self.heartbeat_time = self.clock()
            self.last_heartbeat_at = utcnow()
            return True
        seq = frame.get('acked_seq')
        snapshot_id = frame.get('snapshot_id')
        if (type(seq) is not int or seq < 1 or not isinstance(snapshot_id, str)
                or frame.get('result') != 'APPLIED' or frame.get('data_mode') != 'MOCK'
                or frame.get('simulated') is not True
                or not all(self.valid_stamp(frame.get(k)) for k in ('received_at', 'applied_at'))
                or (seq, snapshot_id) not in self.sent):
            return reject()
        if self.last_acked_seq is not None and seq <= self.last_acked_seq:
            self.duplicates += 1
            return False
        self.receiver_id, self.instance_id = receiver, instance
        self.last_acked_seq = seq
        self.last_ack_at = utcnow()
        self.pending = {k: v for k, v in self.pending.items() if k[0] > seq}
        return True

    def close(self):
        self.connected = False

    def view(self):
        now = self.clock()
        hb_origin = self.heartbeat_time if self.heartbeat_time is not None else self.run_started
        if not self.connected or now - hb_origin > self.HEARTBEAT_TIMEOUT:
            state = 'DISCONNECTED'
        elif self.pending and now - min(self.pending.values()) > self.ACK_TIMEOUT:
            state = 'STALE'
        elif self.last_acked_seq is None:
            state = 'AWAITING_ACK'
        elif self.pending:
            state = 'LAGGING'
        elif self.heartbeat_time is None:
            state = 'AWAITING_ACK'
        else:
            state = 'SYNCED'
        return dict(transport='CONNECTED' if self.connected else 'DISCONNECTED',
                    receiver_state=state, receiver_id=self.receiver_id,
                    receiver_instance_id=self.instance_id, connection_id=self.connection_id,
                    run_id=self.run_id, snapshot_id=self.last_snapshot_id,
                    last_sent_seq=self.last_sent_seq, last_acked_seq=self.last_acked_seq,
                    last_ack_at=self.last_ack_at, last_heartbeat_at=self.last_heartbeat_at,
                    ack_lag_events=None if self.last_acked_seq is None else len(self.pending),
                    ack_timeout_ms=10000, heartbeat_timeout_ms=15000,
                    evidence_mode='LIVE', live_verified=state == 'SYNCED',
                    authenticated=False, authentication_status='UNCONFIGURED',
                    rejected_feedback=self.rejected, ignored_acks=self.duplicates)
