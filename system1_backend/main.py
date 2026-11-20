
import json
from functools import wraps
from threading import RLock
from fastapi import Request
from fastapi.exceptions import RequestValidationError
import json
from threading import RLock
from fastapi.responses import JSONResponse
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from zoneinfo import ZoneInfo
from pydantic import BaseModel
from fastapi import HTTPException

from fastapi import FastAPI
from copy import deepcopy
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
from contextlib import asynccontextmanager
from receiver_tracking import ReceiverSession


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 실행 중 자동 개표 작업을 관리합니다."""

    task = asyncio.create_task(simulation_tick_loop())

    try:
        yield
    finally:
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="P1 Election Data Provider",
    version="0.1.0",
    lifespan=lifespan
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    """입력 검증 오류를 공통 JSON 형식으로 반환합니다."""

    # 오류가 발생한 요청의 JSON 본문
    request_body = exc.body

    request_id = None

    if isinstance(request_body, dict):
        request_id = request_body.get("request_id")

    # 검증 오류의 필요한 정보만 전달
    error_details = [
        {
            "field": ".".join(str(item) for item in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]

    return JSONResponse(
        status_code=422,
        content={
            "ok": False,
            "request_id": request_id,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "요청 데이터 형식이 올바르지 않습니다.",
                "retryable": False,
                "details": {
                    "validation_errors": error_details
                },
            },
        },
    )


@app.get("/api/v0.1/health")
def get_health():
    """SYSTEM 1 서버의 실행 상태를 반환합니다."""
    return {
        "service": "SYSTEM1",
        "status": "UP",
        "observed_at": datetime.now(
            ZoneInfo("Asia/Seoul")
        ).isoformat(),
    }


# SYSTEM 1 교육용 시뮬레이션 초기 데이터
ELECTION_ID = "0020260603"
RUN_ID = "MOCK_RUN_LOCAL_001"

CANDIDATE_IDS = [
    "0020260603_SEOUL_C01",
    "0020260603_SEOUL_C02",
    "0020260603_SEOUL_C04",
    "0020260603_SEOUL_C05",
    "0020260603_SEOUL_C07",
]

# 공식 실제 투표수가 아닌 교육용 목표 투표수입니다.
TARGET_BALLOTS = 10000


def create_initial_snapshot(run_id: str):
    """후보별 득표수와 개표율이 0인 초기 데이터를 생성합니다."""

    return {
        "contract_version": "0.1",
        "contract_status": "PROPOSAL_UNIMPLEMENTED",
        "type": "snapshot",
        "election_id": ELECTION_ID,
        "election_type": "GOVERNOR",
        "run_id": run_id,
        "seq": 1,
        "event_time": datetime.now(
            ZoneInfo("Asia/Seoul")
        ).isoformat(),
        "emitted_at": datetime.now(
            ZoneInfo("Asia/Seoul")
        ).isoformat(),
        "state": "IDLE",
        "snapshot_id": f"{run_id}_S1",
        "data_mode": "MOCK",
        "simulated": True,
        "notice": "교육용 예시이며 역사적 개표 재현이 아닙니다.",
        "reference": {
            "source_snapshot_id": "P1_REAL_FINAL_dd6dba9ecf8b3c6d",
            "dataset_version": "processed_v0.1_20261120",
            "verification_status": "REVIEW_REQUIRED",
            "results_as_of": None,
            "results_as_of_precision": "UNKNOWN",
            "source_ids": [
                "CSV_RESULTS",
                "XLSX_COUNT",
                "XLSX_TURNOUT",
                "XLSX_CANDIDATES",
            ],
        },
        "scope_region_ids": ["SEOUL"],
        "regions": [
            {
                "region_id": "SEOUL",
                "target_ballots": TARGET_BALLOTS,
                "target_ballots_basis": "SCENARIO_FIXED_EDUCATIONAL",
                "counted_votes": 0,
                "valid_votes": 0,
                "invalid_votes": 0,
                "count_rate_pct": 0.0,
                "candidate_votes": [
                    {
                        "candidate_id": candidate_id,
                        "votes": 0,
                        "vote_share_pct": None,
                    }
                    for candidate_id in CANDIDATE_IDS
                ],
            }
        ],
        
        "sync_cursor_seq": 1,
        "catalog": {
            "candidates": [
                {
                    "candidate_id": "0020260603_SEOUL_C01",
                    "candidate_name": "정원오",
                    "ballot_number": 1,
                    "party_name": "더불어민주당",
                    "source_id": "XLSX_CANDIDATES",
                },
                {
                    "candidate_id": "0020260603_SEOUL_C02",
                    "candidate_name": "오세훈",
                    "ballot_number": 2,
                    "party_name": "국민의힘",
                    "source_id": "XLSX_CANDIDATES",
                },
                {
                    "candidate_id": "0020260603_SEOUL_C04",
                    "candidate_name": "김정철",
                    "ballot_number": 4,
                    "party_name": "개혁신당",
                    "source_id": "XLSX_CANDIDATES",
                },
                {
                    "candidate_id": "0020260603_SEOUL_C05",
                    "candidate_name": "유지혜",
                    "ballot_number": 5,
                    "party_name": "여성의당",
                    "source_id": "XLSX_CANDIDATES",
                },
                {
                    "candidate_id": "0020260603_SEOUL_C07",
                    "candidate_name": "권영국",
                    "ballot_number": 7,
                    "party_name": "정의당",
                    "source_id": "XLSX_CANDIDATES",
                },
            ],
            "regions": [
                {
                    "region_id": "SEOUL",
                    "region_name": "서울특별시",
                    "region_level": "CITY",
                    "parent_region_id": None,
                    "source_id": "XLSX_COUNT",
                }
            ],
        },
    }


def mock_percentage(numerator: int, denominator: int):
    """Contract v0.1: integer inputs, six decimal HALF_UP; no zero denominator."""
    if denominator == 0:
        return None
    return float((Decimal(numerator) * 100 / Decimal(denominator)).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP))


def calculate_next_mock_snapshot(current_snapshot: dict):
    """교육용 가상 개표 데이터를 한 단계 계산합니다."""

    snapshot = deepcopy(current_snapshot)
    region = snapshot["regions"][0]

    target = region["target_ballots"]
    counted = region["counted_votes"]

    # 한 단계마다 최대 500표 증가
    increment = min(500, target - counted)

    if increment <= 0:
        return snapshot

    candidate_count = len(region["candidate_votes"])

    if candidate_count != 5:
        raise ValueError("교육용 후보자 수가 5명이 아닙니다.")

    # 교육용 테스트: 5명에게 동일하게 배분
    votes_per_candidate = increment // candidate_count

    for candidate in region["candidate_votes"]:
        candidate["votes"] += votes_per_candidate

    region["counted_votes"] += increment
    region["valid_votes"] = sum(
        candidate["votes"]
        for candidate in region["candidate_votes"]
    )
    region["invalid_votes"] = 0

    region["count_rate_pct"] = mock_percentage(region["counted_votes"], target)

    for candidate in region["candidate_votes"]:
        candidate["vote_share_pct"] = mock_percentage(candidate["votes"], region["valid_votes"])

    snapshot["data_mode"] = "MOCK"
    snapshot["simulated"] = True

    return snapshot


simulation_state = {
    "run_id": RUN_ID,
    "state": "IDLE",
    "seq": 1,
    "snapshot": create_initial_snapshot(RUN_ID),
    "system2": None,
    "data_mode": "MOCK",
    "simulated": True,
}

def record_status_event(reason: str):
    """현재 상태 변경을 별도 이벤트로 기록합니다."""

    now = datetime.now(
        ZoneInfo("Asia/Seoul")
    ).isoformat()

    snapshot = simulation_state["snapshot"]
    simulation_state["last_status_event"] = {
        "contract_version": snapshot["contract_version"],
        "contract_status": snapshot["contract_status"],
        "reference": deepcopy(snapshot["reference"]),
        "type": "status",
        "election_id": ELECTION_ID,
        "election_type": "GOVERNOR",
        "run_id": simulation_state["run_id"],
        "seq": simulation_state["seq"],
        "event_time": now,
        "emitted_at": now,
        "state": simulation_state["state"],
        "reason": reason,
        "data_mode": "MOCK",
        "simulated": True,
        "notice": "교육용 예시이며 역사적 개표 재현이 아닙니다.",
    }

# 연결된 WebSocket 클라이언트 관리
ws_subscribers = {}
receiver_sessions = {}
latest_receiver_session = None


def publish_ws_event(event: dict):
    """연결된 클라이언트 모두에게 이벤트를 예약합니다."""

    # 이 함수는 REST 요청 처리 중 호출됩니다.
    # 실제 WebSocket 전송은 해당 클라이언트의 이벤트 루프가 수행합니다.
    with request_lock:
        for subscriber in ws_subscribers.values():
            loop = subscriber["loop"]
            queue = subscriber["queue"]

            loop.call_soon_threadsafe(
                queue.put_nowait,
                deepcopy(event),
            )


async def send_ws_messages(websocket: WebSocket, queue: asyncio.Queue, session=None):
    """클라이언트별 메시지를 순서대로 전송합니다."""

    while True:
        message = await queue.get()
        if session is not None:
            with request_lock:
                if message.get("run_id") != simulation_state["run_id"]:
                    continue
                message = deepcopy(message)
                if message.get("type") in {"snapshot", "update"}:
                    message["connection_id"] = session.connection_id
                    message["authenticated"] = False
                    session.sent_event(message)
        await websocket.send_json(message)


# 같은 명령이 중복 실행되지 않도록 기록합니다.
request_history = {}
request_lock = RLock()


def idempotent_action(action_name):
    """동일한 request_id의 중복 실행을 방지합니다."""

    def decorator(function):

        @wraps(function)
        def wrapper(request):
            request_data = request.model_dump(mode="json")
            request_id = request_data["request_id"]

            signature = json.dumps(
                {
                    "action": action_name,
                    "body": request_data,
                },
                ensure_ascii=False,
                sort_keys=True,
            )

            # 상태 변경과 요청 기록을 하나의 잠금 안에서 처리
            with request_lock:

                if request_id in request_history:
                    previous = request_history[request_id]

                    if previous["signature"] != signature:
                        return JSONResponse(
                            status_code=409,
                            content={
                                "ok": False,
                                "request_id": request_id,
                                "error": {
                                    "code": "REQUEST_ID_CONFLICT",
                                    "message": "동일한 요청 ID에 다른 내용이 사용되었습니다.",
                                    "retryable": False,
                                    "details": {},
                                },
                            },
                        )

                    # 이전 결과를 반환하며 실제 명령은 재실행하지 않음
                    return previous["response"]

                try:
                    response = function(request)

                except HTTPException as error:
                    code = str(error.detail)
                    response = JSONResponse(
                        status_code=error.status_code,
                        content={
                            "ok": False,
                            "request_id": request_id,
                            "error": {
                                "code": code,
                                "message": code,
                                "retryable": False,
                                "details": {},
                            },
                        },
                    )

                request_history[request_id] = {
                    "signature": signature,
                    "response": response,
                }

                return response

        return wrapper

    return decorator


@app.get("/api/v0.1/simulation/status")
def get_simulation_status():
    """현재 시뮬레이션 상태와 최신 데이터를 반환합니다."""

    with request_lock:
        return {
            "ok": True,
            **deepcopy(simulation_state),
            "system2": latest_receiver_session.view() if latest_receiver_session is not None else None,
            "observed_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        }


class StartSimulationRequest(BaseModel):
    request_id: str
    expected_run_id: str
    election_id: str
    election_type: str
    scenario_id: str
    data_mode: str
    simulated: bool


@app.post("/api/v0.1/simulation/start")
@idempotent_action("start")
def start_simulation(request: StartSimulationRequest):
    """교육용 시뮬레이션을 시작합니다."""

    if request.expected_run_id != simulation_state["run_id"]:
        raise HTTPException(
            status_code=409,
            detail="RUN_MISMATCH",
        )

    if request.election_id != ELECTION_ID:
        raise HTTPException(
            status_code=422,
            detail="UNKNOWN_ELECTION",
        )

    if request.election_type != "GOVERNOR":
        raise HTTPException(
            status_code=422,
            detail="INVALID_ELECTION_TYPE",
        )

    if request.data_mode != "MOCK" or request.simulated is not True:
        raise HTTPException(
            status_code=422,
            detail="UNSUPPORTED_DATA_MODE",
        )

    if request.scenario_id != "MOCK_SEOUL_10000_V01":
        raise HTTPException(
            status_code=422,
            detail="UNKNOWN_SCENARIO",
        )
    

    
    # 완료된 실행 회차는 다시 시작하지 않음
    if simulation_state["state"] == "COMPLETED":
        raise HTTPException(
            status_code=409,
            detail="ALREADY_COMPLETED",
        )

    # 이미 실행 중인 경우 중복 시작 차단
    if simulation_state["state"] == "RUNNING":
        raise HTTPException(
            status_code=409,
            detail="ALREADY_RUNNING",
        )


    simulation_state["state"] = "RUNNING"
    simulation_state["seq"] += 1
    record_status_event("STARTED")
    publish_ws_event(simulation_state["last_status_event"])

    return {
        "ok": True,
        "request_id": request.request_id,
        "run_id": simulation_state["run_id"],
        "state": simulation_state["state"],
        "seq": simulation_state["seq"],
    }

class StopSimulationRequest(BaseModel):
    request_id: str
    expected_run_id: str


@app.post("/api/v0.1/simulation/stop")
@idempotent_action("stop")
def stop_simulation(request: StopSimulationRequest):
    """교육용 시뮬레이션을 중지합니다."""

    if request.expected_run_id != simulation_state["run_id"]:
        raise HTTPException(
            status_code=409,
            detail="RUN_MISMATCH",
        )

    # RUNNING 상태에서만 PAUSED로 변경합니다.
    if simulation_state["state"] == "RUNNING":
        simulation_state["state"] = "PAUSED"
        simulation_state["seq"] += 1
        record_status_event("STOPPED")
        publish_ws_event(simulation_state["last_status_event"])

    return {
        "ok": True,
        "request_id": request.request_id,
        "run_id": simulation_state["run_id"],
        "state": simulation_state["state"],
        "seq": simulation_state["seq"],
    }

from uuid import uuid4


class ResetSimulationRequest(BaseModel):
    request_id: str
    expected_run_id: str


@app.post("/api/v0.1/simulation/reset")
@idempotent_action("reset")
def reset_simulation(request: ResetSimulationRequest):
    """교육용 개표 시뮬레이션을 새 실행 회차로 초기화합니다."""

    previous_run_id = simulation_state["run_id"]

    if request.expected_run_id != previous_run_id:
        raise HTTPException(
            status_code=409,
            detail="RUN_MISMATCH",
        )

    # 새로운 시뮬레이션 실행 ID 생성
    new_run_id = f"MOCK_RUN_{uuid4().hex[:12].upper()}"

    
    # 새로운 실행 회차로 상태 초기화
    simulation_state["run_id"] = new_run_id
    simulation_state["state"] = "IDLE"
    simulation_state["seq"] = 1
    simulation_state["snapshot"] = create_initial_snapshot(new_run_id)
    simulation_state["system2"] = None
    for session in receiver_sessions.values():
        session.reset(new_run_id)

    # 이전 실행의 최신 상태 이벤트는 새 실행에 남기지 않음
    simulation_state.pop("last_status_event", None)

    # Reset으로 생성된 초기 스냅샷임을 명시
    simulation_state["snapshot"]["reason"] = "RESET"
    simulation_state["snapshot"]["previous_run_id"] = previous_run_id
    simulation_state["snapshot"]["sync_cursor_seq"] = 1
    publish_ws_event(simulation_state["snapshot"])


    return {
        "ok": True,
        "request_id": request.request_id,
        "previous_run_id": previous_run_id,
        "run_id": new_run_id,
        "state": "IDLE",
        "seq": 1,
    }


@app.websocket("/ws/v0.1/simulation")
async def simulation_websocket(websocket: WebSocket):
    """초기 스냅샷 및 상태 변경을 실시간 송출합니다."""

    client_role = websocket.query_params.get("client_role")

    
    # Frontend와 SYSTEM 2의 연결을 허용합니다.
    allowed_roles = {"frontend", "system2"}

    if client_role not in allowed_roles:
        await websocket.close(code=1008)
        return


    await websocket.accept()

    global latest_receiver_session
    subscriber_id = uuid4().hex
    session = ReceiverSession(subscriber_id, client_role) if client_role == "system2" else None
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    # 연결 등록과 최초 스냅샷 생성을 함께 처리합니다.
    with request_lock:
        if session is not None:
            session.reset(simulation_state["run_id"])
            receiver_sessions[subscriber_id] = session
            latest_receiver_session = session
        ws_subscribers[subscriber_id] = {
            "loop": loop,
            "queue": queue,
        }

        
        # 재연결 시 최신 개표 데이터와 현재 상태를 함께 전달
        snapshot = deepcopy(simulation_state["snapshot"])

        snapshot["type"] = "snapshot"
        snapshot["state"] = simulation_state["state"]
        # Preserve the data version; only the subscription cursor advances.
        snapshot["sync_cursor_seq"] = simulation_state["seq"]

        # 실제 전송시각은 새로 기록
        snapshot["emitted_at"] = datetime.now(
            ZoneInfo("Asia/Seoul")
        ).isoformat()

        queue.put_nowait(snapshot)


    sender_task = asyncio.create_task(
        send_ws_messages(websocket, queue, session)
    )
    def sender_done(task):
        if not task.cancelled() and task.exception() is not None:
            asyncio.create_task(websocket.close())
    sender_task.add_done_callback(sender_done)

    try:
        # 연결 종료를 감지하기 위한 수신 대기
        while True:
            raw = await websocket.receive_text()
            try:
                frame = json.loads(raw)
            except (ValueError, TypeError):
                if session is not None:
                    session.rejected += 1
                continue
            if session is not None:
                with request_lock:
                    session.receive(frame, simulation_state["run_id"])

    except WebSocketDisconnect:
        pass

    finally:
        # 종료된 클라이언트 제거
        with request_lock:
            ws_subscribers.pop(subscriber_id, None)
            receiver_sessions.pop(subscriber_id, None)
            if session is not None:
                session.close()

        sender_task.cancel()

        try:
            await sender_task
        except (asyncio.CancelledError, WebSocketDisconnect, OSError, RuntimeError):
            pass

async def simulation_tick_loop():
    """RUNNING 상태에서 1초마다 가상 개표를 진행합니다."""

    while True:
        await asyncio.sleep(1)

        with request_lock:
            if simulation_state["state"] != "RUNNING":
                continue

            previous = simulation_state["snapshot"]
            region = previous["regions"][0]

            # 목표 개표수에 도달했다면 추가 계산하지 않음
            if region["counted_votes"] >= region["target_ballots"]:
                continue

            # STEP 17에서 검증한 계산 함수 재사용
            snapshot = calculate_next_mock_snapshot(previous)

            simulation_state["seq"] += 1
            seq = simulation_state["seq"]

            now = datetime.now(
                ZoneInfo("Asia/Seoul")
            ).isoformat()

            snapshot["seq"] = seq
            snapshot["sync_cursor_seq"] = seq
            snapshot["snapshot_id"] = (
                f"{simulation_state['run_id']}_S{seq}"
            )
            snapshot["state"] = "RUNNING"
            snapshot["event_time"] = now
            snapshot["emitted_at"] = now

            # Reset에서만 사용하는 설명 필드 정리
            snapshot.pop("reason", None)
            snapshot.pop("previous_run_id", None)

            # REST 조회용 최신 스냅샷 저장
            simulation_state["snapshot"] = snapshot

            # WebSocket으로 전송할 update 이벤트
            update_event = deepcopy(snapshot)
            update_event["type"] = "update"

            publish_ws_event(update_event)

            # 교육용 목표 투표수에 도달하면 자동 완료 처리
            if (
                snapshot["regions"][0]["counted_votes"]
                >= snapshot["regions"][0]["target_ballots"]
            ):
                simulation_state["state"] = "COMPLETED"

                # REST에서 조회하는 최신 스냅샷에도 완료 상태 반영
                simulation_state["snapshot"]["state"] = "COMPLETED"

                # 완료 상태 이벤트는 별도 순번 사용
                simulation_state["seq"] += 1
                record_status_event("COMPLETED")

                # 완료 상태를 모든 WebSocket 클라이언트에 전송
                publish_ws_event(
                    simulation_state["last_status_event"]
                )
