import asyncio
import os
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from simulation_receiver import DEFAULT_URL, SimulationReceiver


def create_app(receiver=None):
    receiver = receiver or SimulationReceiver(os.getenv("SYSTEM1_WS_URL", DEFAULT_URL))

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(receiver.run())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="P1 Election Newsroom", version="0.1.0", lifespan=lifespan)
    app.state.receiver = receiver

    @app.get("/api/v0.1/health")
    def get_health():
        return {"service": "SYSTEM2", "status": "UP",
                "observed_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat()}

    @app.get("/api/v0.1/simulation/status")
    async def get_simulation_status():
        state = receiver.view()
        snapshot = state["snapshot"]
        return {"ok": True, **state, "service": "SYSTEM2",
                "transport": "CONNECTED" if state["connection"] == "CONNECTED" else "DISCONNECTED",
                "snapshot_id": snapshot["snapshot_id"] if snapshot else None,
                "ack_delivery_status": "SENT_UNCONFIRMED" if state["last_ack_sent_at"] else "NOT_SENT",
                "observed_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat()}

    return app


app = create_app()
