# Offline RHEL 8.10 wheelhouse

Use this when the target server can only reach the company intranet.

## Target assumptions

- RHEL 8.10 or compatible Linux with glibc 2.28
- Python 3.12 from an approved internal source
- A company package mirror or a one-time staging host that can download wheels
- `tmux` installed on the target if watching already-running Claude Code/OpenCode panes
- `Pillow` from the wheelhouse for deterministic PNG/WebP Codex pet atlas validation

## Build the wheelhouse on a connected staging host

From the repository root:

```bash
python3.12 -m pip install --upgrade pip build wheel
python3.12 -m build --wheel
mkdir -p wheelhouse
python3.12 -m pip download \
  --only-binary=:all: \
  --dest wheelhouse \
  -r requirements/rhel8-runtime.txt
cp dist/coding_pet-*.whl wheelhouse/
```

If the staging host is not RHEL 8 compatible, download with explicit target tags:

```bash
python3.12 -m pip download \
  --only-binary=:all: \
  --platform manylinux_2_28_x86_64 \
  --implementation cp \
  --python-version 312 \
  --abi cp312 \
  --abi abi3 \
  --abi none \
  --dest wheelhouse \
  -r requirements/rhel8-runtime.txt
```

Use matching Python and ABI tags if the company later changes the runtime.
The checked-in constraints intentionally cap PySide6 below 6.10 so pip selects
RHEL 8 compatible `manylinux_2_28` wheels instead of newer `manylinux_2_34`
wheels. Pillow is also part of the runtime wheelhouse because `validate-pet`,
`import-pet`, and `set-pet` inspect actual atlas pixels, including empty used
cells, transparent unused cells, alpha channels, and opaque-background mistakes.

## Validate the wheelhouse before transfer

Run this from a source checkout on the staging host after copying
`dist/coding_pet-*.whl` into `wheelhouse/`:

```bash
PYTHONPATH=src python -m coding_pet.cli admin wheelhouse-check wheelhouse \
  --json-out /tmp/coding-pet-wheelhouse.json
```

The command checks for the project wheel plus the runtime wheels `pydantic`,
`typer`, `Pillow`, `PySide6`, `PySide6_Addons`, `PySide6_Essentials`, and
`shiboken6`, rejects wheel filenames tagged for glibc newer than RHEL 8.10's
glibc 2.28, tagged for a non-x86_64 platform, or incompatible with the Python
3.12 target, and performs a temporary `pip install --no-index --find-links
wheelhouse 'coding-pet[gui]'` smoke test that imports `PySide6.QtCore`,
loads the installed `codex-default` theme, and confirms installed systemd unit
files are discoverable.
It also opens the `coding_pet-*.whl` archive and verifies that the packaged
docs, RHEL requirements, systemd units, theme registry, and default pet assets
are present under `share/coding-pet/`.
The JSON report records each wheel's filename, normalized distribution name,
SHA-256, and size in bytes. Required target evidence must include a wheel record
for each required distribution. Keep that report with the transfer record so
the intranet copy can be audited without reaching external package indexes.

For a quick static-only check:

```bash
PYTHONPATH=src python -m coding_pet.cli admin wheelhouse-check wheelhouse \
  --skip-install-smoke \
  --json-out /tmp/coding-pet-wheelhouse-static.json
```

The target evidence bundle can also run the same validation and archive the
result as `wheelhouse.json`:

```bash
PYTHONPATH=src python -m coding_pet.cli admin evidence-bundle \
  --profile target \
  --output-dir /tmp/coding-pet-target-evidence \
  --wheelhouse wheelhouse \
  --require-wheelhouse
```

Use `--skip-install-smoke` there only when the install smoke test must be run in
a separate approved venv; otherwise keep the full offline install check enabled.

## Install on the intranet-only target

Copy `wheelhouse/` and this repository or the built project wheel to the target host, then:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --no-index --find-links wheelhouse 'coding-pet[gui]'
```

For a source checkout:

```bash
python -m pip install --no-index --find-links wheelhouse -e '.[gui]'
```

## Verify without external access

```bash
PYTHONPATH=src python -m coding_pet.cli admin doctor
CODING_PET_DAEMON_ONESHOT=1 PYTHONPATH=src python -m coding_pet.cli daemon run
PYTHONPATH=src python -m coding_pet.cli widget run
```

The daemon and widget do not download dependencies or call external package indexes at runtime.
The monitored agent CLI is still responsible for its own model/provider connectivity.
