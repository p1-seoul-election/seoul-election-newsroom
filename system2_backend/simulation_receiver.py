"""Single-process, memory-only receiver for SYSTEM 1's MOCK stream."""
import asyncio
import json
import logging
from uuid import uuid4
from contextlib import suppress
from copy import deepcopy
from datetime import datetime, timezone

import websockets
from event_validation import validate
from simulation_storage import MemorySimulationStore, SimulationStore

LOG = logging.getLogger(__name__)
INSTANCE_ID = uuid4().hex
DEFAULT_URL = "ws://127.0.0.1:8001/ws/v0.1/simulation?client_role=system2"


class SimulationReceiver:
    def __init__(self, url=DEFAULT_URL, retry_initial=1.0, retry_max=30.0, heartbeat_interval=5.0,
                 *, storage: SimulationStore | None = None):
        self.url = url
        self.receiver_id = "SYSTEM2"
        self.receiver_instance_id = INSTANCE_ID
        self.heartbeat_interval = heartbeat_interval
        self.retry_initial = retry_initial
        self.retry_max = retry_max
        self.storage = storage if storage is not None else MemorySimulationStore()
        self.retired_runs = set()
        self.data = dict(connection="DISCONNECTED", synchronized=False,
                         run_id=None, seq=None, sync_cursor_seq=None, state=None, snapshot=None,
                         last_event=None, received_at=None, last_error=None,
                         connection_count=0, accepted_events=0, ignored_events=0,
                         invalid_events=0, data_mode=None, simulated=None,
                         official_data=False, authenticated=False, authentication_status="UNCONFIGURED",
                         receiver_id=self.receiver_id, receiver_instance_id=self.receiver_instance_id,
                         connection_id=None, feedback_available=False, ack_sent_count=0,
                         last_acked_seq=None, last_ack_sent_at=None, last_heartbeat_sent_at=None,
                         heartbeat_sent_count=0, last_applied_seq=None, last_applied_at=None,
                         storage_state="NOT_READY", validation_state="NOT_TESTED",
                         validation_errors=[], verification_state="REVIEW_REQUIRED",
                         approval_blocked=True, publication_blocked=True)

    def view(self):
        return deepcopy(self.data)

    def apply(self, event, *, initial=False):
        try:
            validate(event, None if isinstance(event, dict) and event.get("type") == "snapshot" else self.data["snapshot"])
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            self.reject(str(error))
            return False
        run, seq, kind = event["run_id"], event["seq"], event["type"]
        old_run, old_seq = self.data["run_id"], self.data["seq"]
        cursor = event["sync_cursor_seq"] if kind == "snapshot" else seq
        if (run in self.retired_runs
                or (initial and kind != "snapshot")
                or (run != old_run and kind != "snapshot")
                or (run == old_run and cursor <= old_seq)):
            # Same-cursor reconnects are handled by same_snapshot after validation.
            self.data["ignored_events"] += 1
            return False
        if kind == "snapshot" and run == old_run:
            old_snapshot = self.data["snapshot"]
            if seq < old_snapshot["seq"]:
                self.data["ignored_events"] += 1
                return False
            if seq == old_snapshot["seq"] and not self.same_data(event):
                self.reject("DATA_VERSION_CONFLICT")
                return False
            try:
                validate(event, old_snapshot)
            except (ValueError, TypeError, KeyError, OverflowError) as error:
                self.reject(str(error))
                return False
        if (run == old_run and kind != "snapshot"
                and (self.data["validation_state"] == "FAIL" or seq != old_seq + 1)):
            self.reject("RESYNC_SNAPSHOT_REQUIRED")
            return False
        if kind == "status" and event["state"] == "COMPLETED":
            r = self.data["snapshot"]["regions"][0]
            if r["counted_votes"] != r["target_ballots"]:
                self.reject("EARLY_COMPLETED")
                return False
        self.storage.apply_validated(event, cursor=cursor, state=self.data,
                                     retired_runs=self.retired_runs)
        return True

    def reject(self, code):
        self.data["invalid_events"] += 1
        self.data.update(validation_state="FAIL", validation_errors=[code],
                         last_error=code, synchronized=False, verification_state="FAIL",
                         approval_blocked=True, publication_blocked=True)

    def same_data(self, event):
        old = self.data["snapshot"]
        return old is not None and all(event.get(k) == old.get(k) for k in
            ("seq", "regions", "catalog", "scope_region_ids", "reference", "snapshot_id"))

    def same_snapshot(self, event):
        try:
            validate(event, self.data["snapshot"])
        except (ValueError, TypeError, KeyError, OverflowError):
            return False
        return (self.data["snapshot"] is not None and event["type"] == "snapshot"
                and event["run_id"] == self.data["run_id"]
                and event["sync_cursor_seq"] == self.data["seq"]
                and event["state"] == self.data["state"]
                and self.same_data(event))

    async def send_ack(self, ws, event, *, applied=False):
        # Called only after accepted atomic apply or verified identical reconnect snapshot.
        if (not applied or event.get("type") not in {"snapshot", "update"}
                or not self.data["connection_id"] or not self.same_applied_data(event)):
            return False
        frame = dict(type="ack", receiver_id=self.receiver_id,
                     receiver_instance_id=self.receiver_instance_id,
                     connection_id=self.data["connection_id"], run_id=event["run_id"],
                     acked_seq=event["seq"], snapshot_id=event["snapshot_id"], result="APPLIED",
                     received_at=self.data["received_at"], applied_at=self.data["last_applied_at"],
                     data_mode="MOCK", simulated=True)
        await ws.send(json.dumps(frame))
        self.data.update(last_acked_seq=event["seq"], last_ack_sent_at=datetime.now(timezone.utc).isoformat())
        self.data["ack_sent_count"] += 1
        return True

    def same_applied_data(self, event):
        snapshot = self.data["snapshot"]
        return (event.get("type") in {"snapshot", "update"}
                and self.data["validation_state"] == "PASS" and snapshot is not None
                and event.get("run_id") == self.data["run_id"]
                and event.get("seq") == snapshot["seq"]
                and event.get("snapshot_id") == snapshot["snapshot_id"]
                and event.get("regions") == snapshot["regions"])

    async def send_heartbeat(self, ws):
        if not self.data["connection_id"] or self.data["run_id"] is None:
            return
        await ws.send(json.dumps(dict(type="heartbeat", receiver_id=self.receiver_id,
            receiver_instance_id=self.receiver_instance_id,
            connection_id=self.data["connection_id"], run_id=self.data["run_id"])))
        self.data["heartbeat_sent_count"] += 1
        self.data["last_heartbeat_sent_at"] = datetime.now(timezone.utc).isoformat()

    async def heartbeat_loop(self, ws):
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            await self.send_heartbeat(ws)

    async def run(self):
        delay = self.retry_initial
        try:
            while True:
                self.data.update(connection="CONNECTING", synchronized=False, connection_id=None,
                                 feedback_available=False, last_acked_seq=None, last_ack_sent_at=None,
                                 last_heartbeat_sent_at=None)
                heartbeat_task = None
                try:
                    async with websockets.connect(self.url, open_timeout=5,
                                                  close_timeout=2, ping_interval=20,
                                                  ping_timeout=20) as ws:
                        self.data["connection_count"] += 1
                        # Every connection must start with a complete snapshot.
                        event = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                        accepted = self.apply(event, initial=True)
                        same_snapshot = self.same_snapshot(event)
                        if not accepted and not same_snapshot:
                            raise ValueError("Expected a current MOCK snapshot")
                        self.data.update(connection="CONNECTED", synchronized=True, last_error=None,
                                         validation_state="PASS", validation_errors=[], verification_state="REVIEW_REQUIRED")
                        connection_id = event.get("connection_id")
                        if isinstance(connection_id, str) and connection_id:
                            self.data.update(connection_id=connection_id, feedback_available=True)
                            await self.send_ack(ws, event, applied=accepted or same_snapshot)
                            await self.send_heartbeat(ws)
                            heartbeat_task = asyncio.create_task(self.heartbeat_loop(ws))
                            # A failed sender must close the connection and trigger reconnect.
                            def heartbeat_done(task):
                                if not task.cancelled() and task.exception() is not None:
                                    asyncio.create_task(ws.close())
                            heartbeat_task.add_done_callback(heartbeat_done)
                        delay = self.retry_initial
                        async for message in ws:
                            try:
                                event = json.loads(message)
                                previous_run = self.data["run_id"]
                                accepted = self.apply(event)
                                if accepted:
                                    self.data["synchronized"] = True
                                    await self.send_ack(ws, event, applied=True)
                                    if previous_run != self.data["run_id"]:
                                        await self.send_heartbeat(ws)
                                if self.data["validation_state"] == "FAIL":
                                    raise ValueError("RESYNC_SNAPSHOT_REQUIRED")
                            except (ValueError, TypeError):
                                if self.data["validation_state"] != "FAIL":
                                    self.reject("INVALID_JSON")
                                raise ValueError("RESYNC_SNAPSHOT_REQUIRED") from None
                except (OSError, websockets.exceptions.WebSocketException,
                        ValueError, TypeError, TimeoutError) as error:
                    self.data["last_error"] = type(error).__name__
                    LOG.warning("SYSTEM 1 connection unavailable: %s", type(error).__name__)
                finally:
                    if heartbeat_task is not None:
                        heartbeat_task.cancel()
                        with suppress(asyncio.CancelledError, OSError, websockets.exceptions.WebSocketException):
                            await heartbeat_task
                self.data.update(connection="RECONNECTING", synchronized=False)
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.retry_max)
        finally:
            self.data.update(connection="DISCONNECTED", synchronized=False, feedback_available=False)
