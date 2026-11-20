# 최초 GitHub 업로드 준비

대상 저장소: <https://github.com/p1-seoul-election/seoul-election-newsroom>

이번 작업은 업로드 준비입니다. 실제 commit/push는 실행하지 않았습니다. 기존 코드·테스트·Git 이력·운영 서버는 변경하지 않습니다.

## 확인한 상태

- 로컬 프로젝트는 아직 Git 저장소가 아닙니다. 브랜치·remote·추적 파일이 없고 이번에도 `git init`하지 않았습니다.
- 연결된 GitHub 앱에서는 404가 반환됐습니다. 로컬 GitHub CLI의 인증으로 다시 조회하여 `private=true`, `visibility=private`, 소유자 유형 `Organization`, 기본 브랜치 이름 `main`을 확인했습니다.
- 조직 메타데이터는 public_repos=0, private repository 1개를 보여 줍니다. 조직에 저장소와 동일한 Private 플래그가 있다는 뜻은 아닙니다. 조직 멤버십 공개·팀별 권한·외부 협업자·조직 정책 전체는 검증하지 않았습니다.
- 조회 시점 원격 브랜치 목록은 비어 있었습니다. 저장소 메타데이터 size=0만으로 원격 이력이 없다고 단정하지 않습니다. 첫 commit/push 직전에 원격 브랜치·이력을 다시 확인합니다.
- Private 여부는 조회 시점의 상태입니다. 최초 업로드 직전 다시 확인합니다.

## 첫 커밋 후보: 13개 파일

```text
.gitignore
README.md
requirements.txt
docs/GITHUB_UPLOAD.md
system1_backend/main.py
system1_backend/receiver_tracking.py
system2_backend/main.py
system2_backend/simulation_receiver.py
system2_backend/event_validation.py
system2_backend/test_step24.py
system2_backend/test_step25.py
system2_backend/test_step27.py
system2_backend/test_step28.py
```

`.gitignore`는 이 목록만 허용합니다. 앞으로 파일을 추가할 때는 의도된 공유 범위인지 확인하고 허용 목록을 갱신해야 합니다. `git add -f`로 제외 규칙을 우회하지 않습니다. `.gitignore`는 이미 추적 중인 파일을 자동 제거하지 않으므로, 추후에는 `git ls-files`도 확인합니다.

제외 대상은 `.venv`, 환경변수 파일, 비밀 키·인증 파일, 캐시·로그, 단계별 실제 payload·PID·연결 식별자·사용자 경로, STEP26/STEP29 진단 디렉터리와 내부 기획·계약 사본, 공식 원자료·정제 데이터입니다. 로컬 자료는 삭제하지 않습니다. 코드 안의 후보·출처 참조 정보는 가상 개표 숫자의 공식 근거가 아닙니다.

## 검사 결과와 한계

최초 비가상환경 파일 46개의 내용을 검사했습니다. API 토큰·개인키·자격정보를 포함한 URL·비밀번호 할당·주민등록번호 형태의 고위험 패턴은 발견되지 않았습니다. 기존 단계별 자료의 로컬 사용자 경로와 연결 식별자는 최초 업로드 대상에서 제외했습니다.

허용된 최종 13개 파일도 같은 방식으로 검사했으며 비밀값·이메일·로컬 사용자 경로 등의 패턴이 발견되지 않았습니다. 별도 임시 Git 저장소에서 실제 Git 제외 규칙으로 61개 경로를 검사해 허용/제외 오류 0건을 확인했습니다. 패턴 검사는 모든 비밀의 부재를 보증하지 않습니다. 외부 파일명·이메일·공개 후보 이름과 같은 항목의 맥락을 구분하고, 최종 diff는 사람이 확인해야 합니다. 실제 비밀값은 보고서·로그에 복사하지 않습니다.

현재 기능은 API 키 없이 동작합니다. 새 `.env.example`이나 가짜 키 파일을 만들지 않았으며 실제 `.env` 로딩도 구현하지 않았습니다.

## 재현과 테스트

실행 방법과 API·MOCK/실측 구분은 루트 README를 따릅니다. 기존 36개 테스트를 준비 단계에서 다시 실행하고 결과를 아래에 기록합니다.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\system2_backend\.venv\Scripts\python.exe -m unittest discover -s .\system2_backend -p 'test_step2[4578].py' -v
```

결과: 2026-11-20 재실행 **36 PASS / 0 FAIL** (34.261초). 새 가상환경 설치는 NOT_TESTED이며, requirements.txt는 기존 환경에서 관측한 버전입니다. 설치 명령을 성공 실행했다고 주장하지 않습니다.

## 사용자 승인 후 진행할 명령

아래는 안내이며 이번에 실제 로컬 프로젝트에서 실행하지 않았습니다. Windows PowerShell에서 프로젝트 루트로 이동한 상태를 전제로 합니다.

1. 아직 Git 저장소가 아닌지 재확인한 뒤 초기화합니다. 기존 `.git`이 있으면 다시 초기화하거나 삭제하지 않습니다.

```powershell
git rev-parse --show-toplevel
# 여전히 Git 저장소가 아니라는 결과일 때만:
git init -b main
git remote -v
# origin이 없고 다른 설정도 없음을 확인했을 때만:
git remote add origin https://github.com/p1-seoul-election/seoul-election-newsroom.git
git remote -v
git ls-remote origin
git status --short --branch
git remote -v
```

2. `origin`이 없을 때만 추가합니다. 이미 있으면 URL을 먼저 확인하고 임의 변경하지 않습니다.

```powershell
git remote add origin https://github.com/p1-seoul-election/seoul-election-newsroom.git
git remote -v
git ls-remote origin
```

원격 브랜치/커밋이 발견되면 첫 업로드 절차를 멈추고 기존 이력과 합치는 방법을 검토합니다. 강제 push·원격 이력 삭제·자동 unrelated-history 병합은 하지 않습니다. 저장소가 빈 경우에만 다음 절차를 검토합니다.

3. 허용된 파일만 스테이징하고 내용을 다시 확인합니다. 아래 명령은 이번에 실행하지 않았습니다.

```powershell
git add -- .gitignore README.md requirements.txt docs/GITHUB_UPLOAD.md system1_backend/main.py system1_backend/receiver_tracking.py system2_backend/main.py system2_backend/simulation_receiver.py system2_backend/event_validation.py system2_backend/test_step24.py system2_backend/test_step25.py system2_backend/test_step27.py system2_backend/test_step28.py
git diff --cached --name-status
git diff --cached --check
git diff --cached
git status --short --ignored
gh api repos/p1-seoul-election/seoul-election-newsroom --jq '{full_name,private,visibility,default_branch}'
```

4. 스테이징 내용·저장소 Private·원격 빈 상태·접근 권한·테스트 결과를 확인하고 사용자가 별도로 승인한 뒤 commit/push합니다.

```powershell
# 아래 두 명령은 사용자 승인 전 실행 금지:
git commit -m "Initial backend implementation with MOCK simulation and receiver verification"
git push -u origin main
```

작성자 이름·이메일, 조직 쓰기 권한 및 적용되는 브랜치 보호 정책은 최초 commit/push 전에 확인합니다. 이번 작업은 Git 작성자 설정이나 원격 권한을 바꾸지 않습니다.
