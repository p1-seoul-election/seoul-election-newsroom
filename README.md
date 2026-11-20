# Seoul Election Newsroom — 교육용 개표 Backend

2026 서울특별시장 선거 RAG 프로젝트의 SYSTEM 1·2 Backend입니다. 현재 범위는 **교육용 MOCK 개표 생성·WebSocket 송수신·수치 검증·메모리 반영·ACK·Heartbeat**입니다. RAG·LLM·기사 생성·Frontend·DB 저장은 아직 구현하지 않았습니다.

**가상 득표수는 실제 선거의 중간 개표 기록이나 공식 결과가 아닙니다.** 후보·출처 참조가 포함되어도 MOCK 숫자의 공식 근거를 뜻하지 않습니다. API Contract v0.1은 공동 확정 전 제안 상태이며, 코드 구현을 계약 합의나 사람 승인으로 간주하지 않습니다.

## 구조

```text
system1_backend/
  main.py                  # 제어 API, MOCK 생성, WebSocket 송출
  receiver_tracking.py     # 연결별 ACK·Heartbeat 수신 상태
system2_backend/
  main.py                  # 조회 API 및 수신기 수명 관리
  simulation_receiver.py   # 수신·검증·메모리 반영·ACK·Heartbeat
  event_validation.py      # ID·합계·비율·MOCK·커서 검증
  test_step24.py
  test_step25.py
  test_step27.py
  test_step28.py
docs/GITHUB_UPLOAD.md      # 최초 업로드 절차와 확인사항
requirements.txt
```

공식 데이터 원본·정제 파일·내부 기획 문서·이전 실행 기록·개인 환경 파일은 최초 업로드 대상에서 제외합니다. 출처 원장은 별도로 관리하며, 이 저장소가 공식 선거 데이터 배포본이라고 주장하지 않습니다. 기존 STEP 26 진단 테스트는 당시 결함을 재현하는 역사적 자료이므로 현재 회귀 테스트에 포함하지 않습니다.

## 개발 환경과 설치

- Windows 11 PowerShell, Python 3.12, Git.
- 기존 두 가상환경에서 확인한 패키지 버전은 `requirements.txt`에 기록했습니다. 새 환경에서의 설치는 아직 검증하지 않았습니다.
- OpenAI 등 외부 API 키는 현재 기능과 테스트에 필요하지 않습니다. `.env` 자동 로딩은 구현하지 않았습니다.

아래 명령은 프로젝트 루트에서 실행합니다. 기존 `.venv`가 있으면 다시 만들지 말고 필요한 환경인지 먼저 확인합니다.

```powershell
py -3.12 -m venv .\system1_backend\.venv
py -3.12 -m venv .\system2_backend\.venv
.\system1_backend\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
.\system2_backend\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

## 서버 실행

8001·8002를 이미 사용 중이면 아래 명령을 중복 실행하지 않습니다. 두 PowerShell 창을 사용합니다.

SYSTEM 1 — 프로젝트 루트에서:

```powershell
Set-Location .\system1_backend
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8001
```

SYSTEM 2 — 별도 창의 프로젝트 루트에서:

```powershell
Set-Location .\system2_backend
$env:PYTHONDONTWRITEBYTECODE='1'
$env:SYSTEM1_WS_URL='ws://127.0.0.1:8001/ws/v0.1/simulation?client_role=system2'
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8002
```

`SYSTEM1_WS_URL`을 생략하면 위 주소를 사용합니다. 가상환경 활성화 없이 Python 실행 파일을 직접 호출하므로 PowerShell 실행 정책 변경은 필요하지 않습니다. 각 서버는 기본 단일 worker로 실행합니다.

종료는 서버를 실행한 창에서 `Ctrl+C`로 정상 종료합니다. 기존 서버 종료는 사용자 승인 후 진행합니다. 전체 재실행은 SYSTEM 2 종료 → SYSTEM 1 종료 → SYSTEM 1 시작 → SYSTEM 2 시작 순서가 권장됩니다. 메모리 데이터·회차·ACK 이력은 재시작 시 사라질 수 있습니다. `--reload`는 소스 변경으로 자동 재시작하므로 일관된 검증에서는 사용하지 않습니다.

## API

| 서버 | 경로 | 용도 |
|---|---|---|
| SYSTEM 1 | `GET /api/v0.1/health` | 프로세스 생존 |
| SYSTEM 1 | `GET /api/v0.1/simulation/status` | 회차·전역 커서·데이터·수신기 ACK 상태 |
| SYSTEM 1 | `POST /api/v0.1/simulation/start` | IDLE/PAUSED에서 MOCK 진행 |
| SYSTEM 1 | `POST /api/v0.1/simulation/stop` | RUNNING을 PAUSED로 전환 |
| SYSTEM 1 | `POST /api/v0.1/simulation/reset` | 새 run과 0표 snapshot 생성 |
| SYSTEM 1 | `WS /ws/v0.1/simulation?client_role=system2` | SYSTEM 2 구독·ACK·Heartbeat |
| SYSTEM 1 | `WS /ws/v0.1/simulation?client_role=frontend` | 조회용 구독 |
| SYSTEM 2 | `GET /api/v0.1/health` | 프로세스 생존 |
| SYSTEM 2 | `GET /api/v0.1/simulation/status` | 수신·메모리 반영·ACK 송신 상태 |

실행 중인 서버의 `/docs`에서 요청 스키마도 확인할 수 있습니다. 제안 계약의 `/ingestion/status`는 구현하지 않았습니다.

제어 API는 작업 중인 시뮬레이션을 바꿉니다. 실행하려는 대상 서버인지 확인하고, 공유 실행 상태를 임의 Reset하지 않습니다. 시작 요청 예시는 현재 run을 먼저 조회합니다.

```powershell
$base='http://127.0.0.1:8001/api/v0.1'
$current=Invoke-RestMethod "$base/simulation/status"
$body=@{
  request_id=[guid]::NewGuid().ToString()
  expected_run_id=$current.run_id
  election_id='0020260603'
  election_type='GOVERNOR'
  scenario_id='MOCK_SEOUL_10000_V01'
  data_mode='MOCK'
  simulated=$true
} | ConvertTo-Json
Invoke-RestMethod "$base/simulation/start" -Method Post -ContentType 'application/json' -Body $body
```

stop/reset은 `request_id`와 `expected_run_id`를 JSON으로 받습니다. 같은 request_id와 본문 재요청은 같은 결과를 반환하며, ID 재사용 시 본문이 다르면 충돌합니다. COMPLETED 이후 다시 진행하려면 명시적으로 새 run을 생성해야 합니다.

## 수치·ACK·Heartbeat 규칙

- 후보 5명 득표 합 = valid_votes, valid_votes + invalid_votes = counted_votes.
- 개표율은 교육용 `target_ballots` 분모, 후보 득표율은 현재 valid_votes 분모입니다. 정수 원값에서 소수 6자리 HALF_UP으로 계산하며 valid_votes=0이면 득표율은 null입니다. 화면 2자리 표시는 Backend 전송 정밀도와 구분합니다.
- snapshot.seq는 데이터 버전입니다. sync_cursor_seq는 원자적 구독 시점의 전역 이벤트 커서이며 이후 이벤트 연속성은 cursor+1부터 검사합니다.
- 검증 실패 데이터는 마지막 정상 수치를 덮어쓰지 않습니다. 중복·역순 update도 재적용하지 않습니다.
- snapshot/update를 정상 메모리 반영한 뒤만 APPLIED ACK를 보내며 ACK 순번은 데이터 seq입니다. status/error·검증 실패에는 APPLIED ACK를 보내지 않습니다.
- Heartbeat 기본 5초, 미ACK 데이터 10초 초과 시 STALE, Heartbeat 15초 초과 시 DISCONNECTED입니다. 판정은 서버 단조 시계를 사용합니다.
- 수신 상태: AWAITING_ACK / SYNCED / LAGGING / STALE / DISCONNECTED. `ack_lag_events`는 미ACK 데이터 버전 수이며 전역 seq 차이가 아닙니다.
- SYSTEM 2의 `ack_delivery_status=SENT_UNCONFIRMED`는 송신만 확인했다는 뜻입니다. S1의 ACK 수신 결과와 같은 connection/run/snapshot/데이터 버전으로 대조해야 합니다.
- `SYNCED`·`live_verified=true`는 실제 전송 동기화 관측입니다. **인증이나 공식 수치 확정, 사람 승인이 아닙니다.** 현재 `authenticated=false`, 인증 방식은 미구성입니다.
- 참조자료의 REVIEW_REQUIRED와 최상위 승인·발행 차단을 유지합니다. 자동 검증 PASS를 사람 승인으로 해석하지 않습니다.

## 테스트

프로젝트 루트에서:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\system2_backend\.venv\Scripts\python.exe -m unittest discover -s .\system2_backend -p 'test_step2[4578].py' -v
```

총 36건(STEP 24: 6, STEP 25: 9, STEP 27: 10, STEP 28: 11)입니다. 별도 임시 포트에서 WebSocket·독립 서버 프로세스·Start/Stop/Reset/재접속/COMPLETED를 시험하고, 시험이 생성한 프로세스만 종료합니다. 시험용 run의 숫자도 전부 MOCK입니다.

타임아웃 10/15초 경계는 제어 가능한 단조 시계 단위 시험입니다. 실제 네트워크 패킷을 해당 시간 동안 차단하는 장애 시험과 구분합니다. 실행 과정에서 생기는 로컬 JSON·로그·개인 경로는 `.gitignore`로 제외합니다. 최신 준비 단계 실행 결과는 `docs/GITHUB_UPLOAD.md`에 기록합니다.

## 현재 한계

인증·권한·DB·영속 감사 이력·다중 worker·다중 수신기 운영 정책은 미구현입니다. S1의 S2 장애 시 ERROR/생성 중단, 제안 최대 재시도 10초와 실제 30초 등의 차이는 남아 있습니다. 미등록 공식값처럼 보이는 메타데이터와 reference 상태 검증 정책도 후속 정비가 필요합니다. 로컬 개발용으로 사용합니다.

문서·코드를 공유하는 행위가 공식 선거 자료의 재배포 권리나 프로젝트 공동 승인 기록을 대신하지 않습니다. GitHub Private 여부와 접근 권한을 확인한 뒤 최초 업로드 절차를 진행합니다.
