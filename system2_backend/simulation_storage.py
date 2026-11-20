"""Synchronous application of validated events to the receiver read model.

This boundary does not validate, send feedback, or promise durable storage.
Database I/O, restoration and commit/ACK policy remain separate future work.
"""
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Protocol


class SimulationStore(Protocol):
    def apply_validated(self, event: dict[str, Any], *, cursor: int,
                        state: dict[str, Any], retired_runs: set[str]) -> None:
        """Apply an event already accepted by receiver validation and ordering.

        state and retired_runs are receiver-owned mutable read-model objects.
        Calls are synchronous in the existing single-process receiver. Returning
        does not imply a DB commit or authorize an ACK independently of receiver
        checks. Implementations must not perform transport operations.
        """
        ...


class MemorySimulationStore:
    def apply_validated(self, event: dict[str, Any], *, cursor: int,
                        state: dict[str, Any], retired_runs: set[str]) -> None:
        run, seq, kind = event["run_id"], event["seq"], event["type"]
        old_run = state["run_id"]
        if run != old_run and old_run is not None:
            retired_runs.add(old_run)
        if run != old_run:
            state.update(last_acked_seq=None, last_ack_sent_at=None)
        if kind in {"snapshot", "update"}:
            snapshot = deepcopy(event)
            if "catalog" not in snapshot:
                snapshot["catalog"] = deepcopy(state["snapshot"]["catalog"])
            state["snapshot"] = snapshot
            state.update(last_applied_seq=seq, last_applied_at=datetime.now(timezone.utc).isoformat(),
                             storage_state="MEMORY_APPLIED")
        else:
            # Status events have no votes. Preserve the last complete data.
            state["snapshot"]["state"] = event["state"]
        state.update(run_id=run, seq=cursor, sync_cursor_seq=cursor, state=event["state"],
                         last_event=deepcopy(event), data_mode="MOCK", simulated=True,
                         received_at=datetime.now(timezone.utc).isoformat())
        state.update(validation_state="PASS", validation_errors=[],
                         last_error=None, approval_blocked=True, publication_blocked=True)
        state["verification_state"] = "REVIEW_REQUIRED"
        # This stage has no independent human approval or article evidence.
        state["accepted_events"] += 1
