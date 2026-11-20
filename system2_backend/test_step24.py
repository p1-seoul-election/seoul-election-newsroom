import asyncio
import importlib.util
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

from main import create_app
from simulation_receiver import SimulationReceiver


# Use the real initial schema; this imports a separate module without starting a server.
sys.path.append(str(Path(__file__).resolve().parent.parent / "system1_backend"))
spec = importlib.util.spec_from_file_location(
    "provider_step24_fixture", Path(__file__).resolve().parent.parent / "system1_backend" / "main.py")
provider_fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider_fixture)


def event(seq=1, run="A", kind="snapshot", **extra):
    value = provider_fixture.create_initial_snapshot(run)
    value.update(type=kind, seq=seq, sync_cursor_seq=seq, snapshot_id=f"{run}_S{seq}")
    if kind == "status":
        for key in ("regions", "catalog", "scope_region_ids", "snapshot_id"):
            value.pop(key)
        value["reason"] = "TEST"
    value.update(extra)
    return value


async def until(predicate, timeout=8):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(.02)


class StateTests(unittest.TestCase):
    def test_order_and_runs(self):
        r = SimulationReceiver()
        self.assertFalse(r.apply(event(kind="update")))
        self.assertTrue(r.apply(event()))
        # seq counts status events too. A jump directly from 1 to 3 must be blocked.
        self.assertTrue(r.apply(event(2, kind="status")))
        self.assertTrue(r.apply(event(3, kind="update")))
        self.assertFalse(r.apply(event(3)))
        self.assertFalse(r.apply(event(2)))
        self.assertFalse(r.apply(event(4, "B", "status")))
        self.assertTrue(r.apply(event(1, "B")))
        self.assertFalse(r.apply(event(100, "A")))
        self.assertEqual((r.data["run_id"], r.data["seq"]), ("B", 1))

    def test_status_preserves_votes_and_copy(self):
        r = SimulationReceiver()
        self.assertTrue(r.apply(event()))
        original = r.view()["snapshot"]
        status = event(2, kind="status")
        status["state"] = "PAUSED"
        self.assertTrue(r.apply(status))
        self.assertEqual(r.view()["snapshot"]["regions"], original["regions"])
        self.assertEqual(r.view()["snapshot"]["seq"], 1)
        self.assertEqual(r.view()["seq"], 2)
        self.assertEqual(r.view()["state"], "PAUSED")
        view = r.view()
        view["snapshot"]["regions"].clear()
        self.assertTrue(r.view()["snapshot"]["regions"])

    def test_invalid_and_official_rejected(self):
        r = SimulationReceiver()
        for bad in [None, [], {}, event(True), event(0),
                    {**event(), "data_mode": "REAL", "simulated": False},
                    {**event(), "regions": None}, {**event(), "type": "other"}]:
            self.assertFalse(r.apply(bad))
        self.assertIsNone(r.view()["snapshot"])
        self.assertFalse(r.view()["official_data"])


class AsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_reconnect_invalid_frames_and_shutdown(self):
        connections = 0

        async def handler(ws):
            nonlocal connections
            connections += 1
            self.assertEqual(ws.request.path, "/ws/v0.1/simulation?client_role=system2")
            await ws.send(json.dumps(event()))
            if connections == 1:
                await ws.close()
            elif connections == 2:
                # Invalid JSON now requires a new connection/snapshot before updates.
                await ws.send("broken-json")
                await ws.wait_closed()
            else:
                await ws.send(json.dumps(event(2, kind="update")))
                await ws.wait_closed()

        async with websockets.serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            r = SimulationReceiver(f"ws://127.0.0.1:{port}/ws/v0.1/simulation?client_role=system2", .01, .05)
            app = create_app(r)
            async with app.router.lifespan_context(app):
                await until(lambda: r.data["seq"] == 2)
                self.assertGreaterEqual(r.data["connection_count"], 3)
                self.assertEqual(r.data["invalid_events"], 1)
                self.assertTrue(r.data["synchronized"])
            self.assertEqual(r.data["connection"], "DISCONNECTED")

    async def test_upstream_unavailable_health_and_api(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        r = SimulationReceiver(f"ws://127.0.0.1:{port}", .01, .05)
        app = create_app(r)
        async with app.router.lifespan_context(app):
            await until(lambda: r.data["last_error"] is not None)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as c:
                health = await c.get("/api/v0.1/health")
                self.assertEqual(health.status_code, 200)
                self.assertEqual(health.json()["service"], "SYSTEM2")
                self.assertEqual(health.json()["status"], "UP")
                self.assertTrue(health.json()["observed_at"])
                state = (await c.get("/api/v0.1/simulation/status")).json()
                self.assertIsNone(state["snapshot"])
                self.assertFalse(state["synchronized"])

    async def test_system1_regression_and_system2_end_to_end(self):
        root = Path(__file__).resolve().parent.parent
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app",
                                    "--host", "127.0.0.1", "--port", str(port)],
                                   cwd=root / "system1_backend", env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f"http://127.0.0.1:{port}/api/v0.1"
        ws_url = f"ws://127.0.0.1:{port}/ws/v0.1/simulation"
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                async with asyncio.timeout(10):
                    while True:
                        try:
                            response = await c.get(base + "/health")
                            if response.status_code == 200:
                                break
                        except httpx.ConnectError:
                            pass
                        await asyncio.sleep(.05)
                self.assertEqual(response.json()["service"], "SYSTEM1")
                r = SimulationReceiver(ws_url + "?client_role=system2", .01, .05)
                app = create_app(r)
                async with app.router.lifespan_context(app), websockets.connect(ws_url + "?client_role=frontend") as frontend:
                    first = json.loads(await frontend.recv())
                    await until(lambda: r.data["run_id"] == first["run_id"])
                    reset = await c.post(base + "/simulation/reset", json=dict(request_id=uuid4().hex, expected_run_id=first["run_id"]))
                    self.assertEqual(reset.status_code, 200)
                    run = reset.json()["run_id"]
                    await until(lambda: r.data["run_id"] == run)
                    body = dict(request_id=uuid4().hex, expected_run_id=run,
                                election_id="0020260603", election_type="GOVERNOR",
                                scenario_id="MOCK_SEOUL_10000_V01", data_mode="MOCK", simulated=True)
                    start = await c.post(base + "/simulation/start", json=body)
                    repeated = await c.post(base + "/simulation/start", json=body)
                    self.assertEqual(start.status_code, 200)
                    self.assertEqual(start.json(), repeated.json())
                    await until(lambda: r.data["last_event"]["type"] == "update")
                    while True:
                        front = json.loads(await asyncio.wait_for(frontend.recv(), 5))
                        if front["type"] == "update":
                            break
                    self.assertEqual(front["regions"], r.data["snapshot"]["regions"])
                    stop = await c.post(base + "/simulation/stop", json=dict(request_id=uuid4().hex, expected_run_id=run))
                    self.assertEqual(stop.status_code, 200)
                    await until(lambda: r.data["state"] == "PAUSED")
                    current = (await c.get(base + "/simulation/status")).json()
                    self.assertEqual(current["seq"], r.data["seq"])
                    async with websockets.connect(ws_url + "?client_role=system2") as reconnect:
                        snapshot = json.loads(await reconnect.recv())
                        self.assertEqual(snapshot["sync_cursor_seq"], r.data["seq"])
                        self.assertEqual(snapshot["seq"], r.data["snapshot"]["seq"])
                        self.assertEqual(snapshot["regions"], r.data["snapshot"]["regions"])
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as api:
                        state = (await api.get("/api/v0.1/simulation/status")).json()
                        self.assertEqual(state["state"], "PAUSED")
                        self.assertEqual(state["data_mode"], "MOCK")
                        self.assertTrue(state["simulated"])
                        self.assertFalse(state["official_data"])
        finally:
            process.terminate()
            await asyncio.to_thread(process.wait, 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
