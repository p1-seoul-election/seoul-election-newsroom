# Fixture 보존 및 재생 차이 기록
작성: 2026-11-20

## 실제 사용 원본
API Contract:
https://docs.google.com/document/d/1vMOeigbBAZD91P0HvVsPa5XmN59aqdlBMkszTRm5b4g/edit
MOCK Fixture:
https://drive.google.com/file/d/1NixRbD5e0k7gA3czM9dheUcQu_2fkV_Z/view
Fixture 로컬 SHA-256:
096E78FD35CA21D8F26CCF486778ED152B5E3B86A9D5F22A80B708E03F293BAD

수업용 Google Drive 연결로 읽은 원본 JSON을 바이트 그대로 저장했다. 원본을 수정하지 않았다.
정제 데이터 및 Data Dictionary 링크도 조회되었지만 화면의 숫자·catalog는 MOCK Fixture를 기준으로 사용했다.
실제 REAL_FINAL 수치를 MOCK 개표수로 변환하지 않았다. 결과 확정시각 null/UNKNOWN, REVIEW_REQUIRED를 유지한다.

## 원본 불일치·독립 시나리오
- normal.frames seq=2, event_time=15:00:01의 system2.last_sent_seq=3이며 heartbeat는 15:00:03이다. 미래 순번·시각 참조이다.
- normal 마지막 status는 seq=4인데 error.frame은 seq=6, disconnected.frame은 seq=7이다. 각 시나리오는 독립 사례이며 통째로 연속 스트림으로 재생할 수 없다.
- error.invalid_incoming_update는 seq=3/snapshot S3을 재사용하며 counted_votes=2019로 고의 합계 오류이다.
- reset.frame은 15:00:30이지만 system2.last_heartbeat_at=15:00:03이다. 실제 시간초과 증거가 아니다.
- fixture의 emitted_at과 event_time은 모두 예시 시각이며 실제 송출시각이 아니다.

## MOCK 재생 오버레이 (원본 변경 없음)
MockAdapter는 매 이벤트를 복제하고 현재 run_id와 증가 seq를 부여하며 snapshot_id를 실행에 맞게 만든다.
RESET마다 고유 MOCK_RUN_*을 발급한다. 숫자·후보/지역 ID·reference는 원본 그대로 사용한다.
초기 receiver last_sent_seq=1, heartbeat=null로 준비 상태를 표시한다.
ACK 상태의 last_sent_seq/last_acked_seq는 재생 중 데이터 버전에 맞춘다.
LAGGING/STALE은 별도 로컬 시연 상태이며 원본에 없던 선거 수치를 생성하지 않는다.
STOP/재개 시각은 원본 예시를 유지하므로 시각이 역행할 수 있다. 로그는 수신 순(최신 우선)이며 실제 시계가 아니다.
오류 입력은 수치 검증을 먼저 실행해 이미 알려진 seq라도 합계 오류 자체를 검사할 수 있다.
오류 입력 REJECTED는 적용된 서버 이벤트가 아니므로 다음 error frame과 로컬 순번이 같을 수 있다.
seq 누락/다른 run/중복 처리와 sync_cursor_seq 재동기화는 단위 테스트로 검증했다.
100% COMPLETED 샘플은 제공되지 않았다. 정상 Fixture 재생 끝은 PAUSED로 표시한다.
