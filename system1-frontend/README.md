# SYSTEM 1 Frontend v0.4.1 — 진욱님 전달 안내

전달 범위: 기존 프런트엔드 소스, MOCK, 테스트 및 실행 설정. Backend 연결·검증은 이진욱 담당. 이번 전달에서 Adapter/Backend/데이터 로직을 변경하지 않습니다.

## 공동 저장소 위치
저장소 루트의 system1-frontend/에 추가합니다. 기존 system1_backend/, system2_backend/, 루트 README 및 requirements.txt를 덮어쓰지 않습니다.

## 새 PC 실행 (Windows PowerShell)
Node.js와 npm이 설치된 환경에서 system1-frontend 폴더로 이동합니다.
```powershell
New-Item -ItemType Directory -Force .runtime | Out-Null
$env:TEMP = Join-Path (Get-Location) '.runtime'
$env:TMP = $env:TEMP
npm ci
.\run.ps1 dev
```
개발 화면: http://127.0.0.1:5173
검증: .\run.ps1 build / .\run.ps1 test / .\run.ps1 test:e2e
브라우저 테스트는 playwright.config.ts에 지정된 설치된 Microsoft Edge를 사용합니다. 다른 PC에서는 해당 실행 파일 경로를 확인해야 합니다.

## 현재 동작과 연결 경계
현재 UI는 MOCK Demo Mode입니다. 정상 fixture는 2,020표/20.20% 후 PAUSED. 실제 Backend 연결 성공이나 180초 자동 개표 구현을 의미하지 않습니다.
- src/main.tsx: 화면과 현재 MOCK Adapter 선택
- src/mock-adapter.ts: MOCK 동작
- src/live-adapter.ts: 별도로 준비된 RestWebSocketAdapter와 LiveConfig
- src/types.ts, src/validation.ts: 이벤트 타입 및 수신 데이터 검증
- docs/api-contract-v0.1.txt: 기존 제안 계약
현재 화면에 실제 서버 모드 전환 기능이 연결되어 있지 않습니다. 진욱님이 실제 Backend 계약에 맞춰 Adapter 선택·주소 설정·응답/이벤트 매핑 및 연동 검증을 진행합니다.

## 업로드 포함/제외
포함: src/, tests/, package.json, package-lock.json, index.html, TypeScript/Vite/Vitest/Playwright 설정, .npmrc, run.ps1, .gitignore, 실행 안내, API 계약·fixture 설명.
제외: node_modules/, dist/, .runtime/, test-results/, docs/backups/, 이전 전체 화면 증빙, 개인 환경 파일 및 Drive 전달 이력. 기존 로컬 자료는 삭제하지 않습니다.
화면 버전은 v0.4.1이며 package.json의 기존 버전 0.4.0은 의존성과 함께 그대로 보존합니다.

## 기존 검증 기록
2026-11-20 v0.4.1: TypeScript/빌드 PASS, 단위 테스트 32개 PASS, 브라우저 테스트 12개 PASS, 1920×1080·1366×768·390×844 화면 검증. 이는 해당 날짜의 로컬 MOCK 검증 결과이며 진욱님 Backend와의 통합 검증 결과가 아닙니다.
