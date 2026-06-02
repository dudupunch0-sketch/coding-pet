# LLM Target Execution Runbook

Last updated: 2026-06-02

이 문서는 사내 RHEL 8.10 서버에서 LLM 실행자가 `coding-pet`을 설치,
검증, 증빙 수집까지 수행하기 위한 절차다. 대상 서버는 외부 인터넷에
직접 접근하지 않는다고 가정한다. Codex는 대상 서버의 필수 backend가
아니다. 최종 대상 backend는 Claude Code와 OpenCode다.

## 실행 원칙

- 모든 명령은 대상 RHEL 8.10 x86_64 사용자 세션에서 실행한다.
- 외부 인터넷을 사용하지 않는다. wheel, pet ZIP, 문서, source checkout은
  외부 staging 장비에서 미리 반입된 파일만 사용한다.
- Python은 3.12.x만 사용한다. Python 3.6 또는 시스템 기본 Python으로
  설치하거나 검증하지 않는다.
- glibc는 RHEL 8.10의 2.28이어야 한다.
- 기본 내장 sprite는 `codex-default`다. 제거된 legacy `company-pet`
  테마 또는 `/company-pet/` asset 경로가 target evidence에 남으면
  `admin target-evidence-check`가 실패해야 정상이다.
- 실패한 명령은 건너뛰지 말고, 명령, stdout, stderr, 생성된 JSON 경로를
  기록한 뒤 중단한다.

## 반입되어야 하는 입력물

외부 staging 장비에서 직접 업로드용 bundle을 만들 수 있다.

```bash
cd /path/to/coding-pet
python3 scripts/build_airgap_transfer_bundle.py \
  --output-dir /tmp/coding-pet-transfer \
  --wheelhouse /path/to/wheelhouse \
  --pet-staging /path/to/downloaded-pets \
  --replace
```

`--wheelhouse`와 `--pet-staging`은 준비된 경우에만 넣는다. 생성물은 다음과
같다.

```text
/tmp/coding-pet-transfer/coding-pet-airgap-transfer/
/tmp/coding-pet-transfer/coding-pet-airgap-transfer.tar.gz
/tmp/coding-pet-transfer/coding-pet-airgap-transfer/TRANSFER_MANIFEST.sha256
```

대상 서버로 tarball을 직접 업로드한 뒤 무결성을 확인한다.

```bash
mkdir -p /opt
tar -xzf coding-pet-airgap-transfer.tar.gz -C /opt
cd /opt/coding-pet-airgap-transfer
sha256sum -c TRANSFER_MANIFEST.sha256
```

대상 서버의 작업 디렉터리를 먼저 고정한다.

```bash
export APP_ROOT=${APP_ROOT:-/opt/coding-pet-airgap-transfer}
export WHEELHOUSE="$APP_ROOT/wheelhouse"
export PET_STAGING="$APP_ROOT/downloaded-pets"
export PETS_ROOT="$HOME/.codex/pets"
export EVIDENCE_DIR="$APP_ROOT/target-evidence"
export VENV="$APP_ROOT/.venv"
```

반입 파일은 다음을 포함해야 한다.

```text
$APP_ROOT/README.md
$APP_ROOT/pyproject.toml
$APP_ROOT/requirements.txt
$APP_ROOT/src/
$APP_ROOT/assets/sprites/theme-manifest.json
$APP_ROOT/assets/sprites/theme-registry.json
$APP_ROOT/assets/sprites/codex-default/*.png
$APP_ROOT/packaging/systemd/*.service
$APP_ROOT/packaging/systemd/coding-pet.target
$APP_ROOT/packaging/systemd/coding-pet.service.env.example
$APP_ROOT/docs/operations/*.md
$APP_ROOT/requirements/*.txt
$WHEELHOUSE/*.whl
```

petdex.crafter.run 또는 codex-pets.net에서 가져온 pet을 사용할 경우,
외부 staging 장비에서 ZIP과 metadata JSON을 만든 뒤 `$PET_STAGING`에
반입한다. 대상 서버에서 사이트에 접속하지 않는다.

## 1. 대상 환경 확인

```bash
cd "$APP_ROOT"
cat /etc/redhat-release
uname -m
ldd --version | head -n 1
command -v python3.12
python3.12 --version
command -v tmux
command -v notify-send
command -v systemctl
command -v systemd-analyze
command -v claude
command -v opencode
```

필수 기대값:

```text
/etc/redhat-release: Red Hat Enterprise Linux release 8.10
uname -m: x86_64
ldd: glibc 2.28
python3.12 --version: Python 3.12.x
claude: installed
opencode: installed
```

GUI 사용자 세션 값도 확인한다.

```bash
printf 'DISPLAY=%s\n' "${DISPLAY:-}"
printf 'WAYLAND_DISPLAY=%s\n' "${WAYLAND_DISPLAY:-}"
printf 'XDG_RUNTIME_DIR=%s\n' "${XDG_RUNTIME_DIR:-}"
printf 'DBUS_SESSION_BUS_ADDRESS=%s\n' "${DBUS_SESSION_BUS_ADDRESS:-}"
systemctl --user status --no-pager
```

`XDG_RUNTIME_DIR`, `DBUS_SESSION_BUS_ADDRESS`, 그리고 `DISPLAY` 또는
`WAYLAND_DISPLAY` 중 하나가 비어 있으면 systemd user GUI 검증은 통과할
수 없다.

## 2. venv와 offline wheel 설치

```bash
cd "$APP_ROOT"
python3.12 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade --no-index --find-links "$WHEELHOUSE" pip
"$VENV/bin/python" -m pip install --no-index --find-links "$WHEELHOUSE" -r requirements.txt
"$VENV/bin/python" -m pip install --no-index --find-links "$WHEELHOUSE" 'coding-pet[gui]'
```

source checkout 기준으로 직접 검증해야 하면 다음을 사용한다.

```bash
"$VENV/bin/python" -m pip install --no-index --find-links "$WHEELHOUSE" -r requirements.txt
"$VENV/bin/python" -m pip install --no-index --find-links "$WHEELHOUSE" -e '.[gui]'
```

설치 후 명령을 고정한다.

```bash
export CODING_PET_PYTHON="$VENV/bin/python"
export CODING_PET_CMD="$VENV/bin/python -m coding_pet.cli"
"$VENV/bin/python" -m coding_pet.cli admin doctor
```

`admin doctor`에서 최소한 다음이 보여야 한다.

```text
theme=codex-default
theme_missing_assets=none
backend_claude_code=available:...
backend_opencode=available:...
```

## 3. wheelhouse 증빙 생성

```bash
mkdir -p "$EVIDENCE_DIR"
"$VENV/bin/python" -m coding_pet.cli admin wheelhouse-check "$WHEELHOUSE" \
  --json-out "$EVIDENCE_DIR/wheelhouse.json"
```

성공 조건:

```text
wheelhouse=ok
install_smoke=ok
```

이 JSON은 project wheel, runtime dependency wheels, SHA-256, RHEL 8.10
호환 tag, installed PySide6 import, installed `codex-default` theme,
installed systemd shared-data 파일을 검증한다.

## 4. pet package 반입과 선택

기본 테마만 사용하면 이 단계는 검증만 수행한다.

```bash
"$VENV/bin/python" -m coding_pet.cli admin inspect-pet codex-default
```

외부에서 가져온 Codex/Petdex 호환 pet ZIP을 사용할 경우:

```bash
mkdir -p "$PETS_ROOT"
"$VENV/bin/python" -m coding_pet.cli admin validate-pet-batch "$PET_STAGING" \
  --json-out "$EVIDENCE_DIR/pet-package-validation.json"
"$VENV/bin/python" -m coding_pet.cli admin import-pet-batch "$PET_STAGING" \
  --pets-root "$PETS_ROOT" \
  --json-out "$EVIDENCE_DIR/pet-package-import.json"
```

선택한 pet id를 확인한다.

```bash
"$VENV/bin/python" -m coding_pet.cli admin list-pets
export CODING_PET_THEME=codex-default
```

승인된 외부 pet을 기본으로 쓸 때만 `CODING_PET_THEME`를 해당 pet id로
바꾼다.

```bash
export CODING_PET_THEME=<approved-pet-id>
"$VENV/bin/python" -m coding_pet.cli admin doctor
"$VENV/bin/python" -m coding_pet.cli admin inspect-pet "$CODING_PET_THEME"
```

성공 조건:

```text
theme=<approved-pet-id>
theme_format=codex_pet
theme_missing_assets=none
```

## 5. agent hook 설치

Claude Code와 OpenCode 설정 경로가 사내 표준과 다르면 명시적으로 넘긴다.

```bash
export HOOKS_DIR="$HOME/.config/coding-pet/hooks"
export CLAUDE_SETTINGS="$HOME/.claude/settings.json"
export OPENCODE_PLUGIN="$HOME/.config/opencode/plugin/coding-pet.js"

"$VENV/bin/python" -m coding_pet.cli admin install-agent-hooks \
  --hooks-dir "$HOOKS_DIR" \
  --claude-settings "$CLAUDE_SETTINGS" \
  --opencode-plugin "$OPENCODE_PLUGIN"

"$VENV/bin/python" -m coding_pet.cli admin agent-hooks-doctor \
  --hooks-dir "$HOOKS_DIR" \
  --claude-settings "$CLAUDE_SETTINGS" \
  --opencode-plugin "$OPENCODE_PLUGIN" \
  --json-out "$EVIDENCE_DIR/agent-hooks.json"
```

성공 조건:

```text
agent_hooks=ok
```

## 6. systemd user service 구성

```bash
mkdir -p "$HOME/.config/coding-pet" "$HOME/.config/systemd/user"
cat > "$HOME/.config/coding-pet/service.env" <<EOF
CODING_PET_REPO=$APP_ROOT
CODING_PET_PYTHON=$VENV/bin/python
CODING_PET_THEME=$CODING_PET_THEME
CODING_PET_CODEX_PETS_DIR=$PETS_ROOT
CODING_PET_ASSETS_DIR=$APP_ROOT/assets/sprites
CODING_PET_TRANSCRIPT_ENABLED=true
CODING_PET_TRANSCRIPT_REDACT_SECRETS=true
EOF

cp "$APP_ROOT/packaging/systemd/coding-pet-daemon.service" "$HOME/.config/systemd/user/"
cp "$APP_ROOT/packaging/systemd/coding-pet-widget.service" "$HOME/.config/systemd/user/"
cp "$APP_ROOT/packaging/systemd/coding-pet.target" "$HOME/.config/systemd/user/"

systemd-analyze --user verify \
  "$HOME/.config/systemd/user/coding-pet-daemon.service" \
  "$HOME/.config/systemd/user/coding-pet-widget.service" \
  "$HOME/.config/systemd/user/coding-pet.target"

systemctl --user daemon-reload
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY \
  DBUS_SESSION_BUS_ADDRESS XDG_RUNTIME_DIR
systemctl --user enable --now coding-pet.target
```

서비스 상태를 확인한다.

```bash
systemctl --user is-enabled coding-pet.target
systemctl --user is-active coding-pet-daemon.service
systemctl --user is-active coding-pet-widget.service
journalctl --user -u coding-pet-daemon.service -u coding-pet-widget.service \
  -n 100 --no-pager
```

성공 조건:

```text
coding-pet.target: enabled
coding-pet-daemon.service: active
coding-pet-widget.service: active
```

## 7. backend tmux 실증 준비

테스트용 tmux session을 Claude Code와 OpenCode 각각 하나씩 준비한다.
기존 업무 session에 승인/거절 문구를 보내지 말고 disposable session을
사용한다.

```bash
tmux new-session -d -s coding-pet-claude-target 'claude'
tmux new-session -d -s coding-pet-opencode-target 'opencode'
tmux list-panes -a -F '#{session_name}:#{window_index}.#{pane_index} #{pane_id} #{pane_current_command}'
```

아래 명령의 pane 값은 실제 `tmux list-panes` 결과로 바꾼다.

```bash
export CLAUDE_PANE=coding-pet-claude-target:0.0
export OPENCODE_PANE=coding-pet-opencode-target:0.0
```

## 8. target evidence bundle 생성

먼저 backend approve/reject/send_reply 실증을 수집한다.

```bash
"$VENV/bin/python" -m coding_pet.cli admin collect-target-backend-evidence \
  --output-dir "$EVIDENCE_DIR" \
  --claude-pane "$CLAUDE_PANE" \
  --opencode-pane "$OPENCODE_PANE"
```

그 다음 전체 target bundle을 생성한다.

```bash
"$VENV/bin/python" -m coding_pet.cli admin evidence-bundle \
  --profile target \
  --output-dir "$EVIDENCE_DIR" \
  --wheelhouse "$WHEELHOUSE" \
  --require-wheelhouse \
  --pet-source "$PET_STAGING" \
  --require-pet-packages \
  --hooks-dir "$HOOKS_DIR" \
  --claude-settings "$CLAUDE_SETTINGS" \
  --opencode-plugin "$OPENCODE_PLUGIN" \
  --require-agent-hooks
```

외부 pet staging을 사용하지 않는 배포라면 `--pet-source`와
`--require-pet-packages`를 제거한다. pet을 release gate로 삼는 경우에는
반드시 유지한다.

필수 산출물:

```text
$EVIDENCE_DIR/summary.json
$EVIDENCE_DIR/acceptance-target.json
$EVIDENCE_DIR/environment.json
$EVIDENCE_DIR/tmux-control.json
$EVIDENCE_DIR/systemd-units.json
$EVIDENCE_DIR/systemd-runtime.json
$EVIDENCE_DIR/widget-smoke.json
$EVIDENCE_DIR/hook-event-smoke.json
$EVIDENCE_DIR/wheelhouse.json
$EVIDENCE_DIR/agent-hooks.json
$EVIDENCE_DIR/backend-summary.json
$EVIDENCE_DIR/backend-claude_code-send_reply.json
$EVIDENCE_DIR/backend-claude_code-approve.json
$EVIDENCE_DIR/backend-claude_code-reject.json
$EVIDENCE_DIR/backend-opencode-send_reply.json
$EVIDENCE_DIR/backend-opencode-approve.json
$EVIDENCE_DIR/backend-opencode-reject.json
```

## 9. 최종 gate 실행

```bash
"$VENV/bin/python" -m coding_pet.cli admin target-evidence-check "$EVIDENCE_DIR" \
  --json-out "$EVIDENCE_DIR/target-check.json"
```

성공 조건:

```text
target_evidence=ok
backend_report_count=6
```

`target-check.json`의 `ok`가 `true`이고 `errors`가 빈 배열이어야 한다.

## 10. 실패 시 판단 기준

- `environment python.version must be 3.12.x`: Python 3.6 또는 3.11로 실행한
  것이다. venv를 Python 3.12로 다시 만든다.
- `environment libc.version must be exactly 2.28`: 대상이 RHEL 8.10 glibc
  기준이 아니다. wheel 호환성 판단을 중단한다.
- `environment platform.release must describe RHEL 8.10`: target profile을
  현재 WSL 또는 다른 Linux에서 대신 만들고 있다. 실제 RHEL 8.10에서 다시
  수집한다.
- `widget_smoke gui_validated must be true`: GUI user session, PySide6 runtime,
  DISPLAY/WAYLAND/DBUS 환경이 부족하다.
- `systemd_runtime ... DISPLAY or WAYLAND_DISPLAY`: user service에 GUI 환경이
  import되지 않았다.
- `environment theme.name must not use removed legacy theme company-pet`:
  `CODING_PET_THEME` 또는 service.env가 구버전 테마를 가리킨다.
- `widget_smoke ... removed legacy theme asset`: widget이 `/company-pet/`
  경로의 제거된 sprite를 렌더링하고 있다.
- `backend_report_count`가 6보다 작음: Claude Code/OpenCode의
  send_reply/approve/reject 실증 중 일부가 누락됐다.
- `wheelhouse install_smoke=failed`: wheelhouse에 필요한 dependency wheel이
  빠졌거나 RHEL 8.10/Python 3.12 호환 wheel이 아니다.

## 최종 보고 형식

LLM 실행자는 완료 후 다음 항목만 보고한다.

```text
result=<ok|failed>
host=<hostname>
redhat_release=<contents of /etc/redhat-release>
python=<python3.12 --version>
glibc=<ldd --version first line>
theme=<CODING_PET_THEME>
evidence_dir=<absolute path>
target_check=<absolute path to target-check.json>
errors=<empty or concise list>
```

`result=ok`는 `admin target-evidence-check`가 성공한 경우에만 사용한다.
