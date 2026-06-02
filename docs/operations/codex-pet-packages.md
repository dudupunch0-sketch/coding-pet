# Codex pet package compatibility

This project can use Codex-style pet packages copied in by the user. The target
company server does not need to access external pet sites directly.

## Supported layout

Put downloaded pets under:

```text
~/.codex/pets/<pet-id>/
  pet.json
  spritesheet.webp
```

PNG spritesheets are also accepted:

```text
~/.codex/pets/<pet-id>/
  pet.json
  spritesheet.png
```

Petdex API downloads sometimes name the manifest `petjson.json`. The loader
accepts either `pet.json` or `petjson.json`, and `import-pet`/`import-pet-batch`
ensure the installed package also has a Codex-compatible `pet.json`.

The admin commands also accept copied ZIP downloads. A ZIP may contain
`pet.json` or `petjson.json` at the archive root or under one top-level
directory. ZIPs are extracted into a temporary directory for validation, must
contain exactly one pet manifest, and are rejected if any member uses `..`,
absolute paths, drive or stream syntax, or symlinks.

Set the active pet:

```bash
export CODING_PET_THEME=<pet-id>
```

If the company requires a different import directory:

```bash
export CODING_PET_CODEX_PETS_DIR=/approved/path/codex-pets
export CODING_PET_THEME=<pet-id>
```

Add the same values to `~/.config/coding-pet/service.env` for systemd user
services.

## Manifest fields

The compatibility loader accepts a `pet.json` with:

```json
{
  "id": "example-pet",
  "displayName": "Example Pet",
  "spritesheetPath": "spritesheet.webp"
}
```

The loader also accepts `spriteSheetPath`, `spritesheet`, or `atlas` as the
spritesheet field name. Paths must be relative and stay inside the pet package
directory.
Optional layout fields such as `columns`, `rows`, `framesPerState`,
`frameDurationMs`, `frame.width`, and `frame.height` may be omitted for
inference/defaults, but when present they must be positive integers. Invalid
explicit layout values fail validation instead of being silently replaced.

If no animation-state metadata is present, the loader first checks the local
spritesheet size when the file is available. A 1728x1664 atlas with 192x208
frames is inferred as the Petdex 9-column by 8-row contract even when the
manifest only contains `id`, `displayName`, and `spritesheetPath`. A 1536x1872
atlas is inferred as the Codex 8-column by 9-row contract. If the spritesheet is
missing or the size cannot be read yet, the package falls back to the Codex
layout and validation later reports the missing or mismatched asset.

Default Codex state-row mapping:

```text
0 idle
1 running-right
2 running-left
3 waving
4 jumping
5 failed
6 waiting
7 running
8 review
```

Default Codex row timing:

```text
idle          280,110,110,140,140,320 ms
running-right 120,120,120,120,120,120,120,220 ms
running-left  120,120,120,120,120,120,120,220 ms
waving        140,140,140,280 ms
jumping       140,140,140,140,280 ms
failed        140,140,140,140,140,140,140,240 ms
waiting       150,150,150,150,150,260 ms
running       120,120,120,120,120,220 ms
review        150,150,150,150,150,280 ms
```

coding-pet maps its moods onto those Codex rows:

```text
idle      -> idle
typing    -> running
celebrate -> jumping
alert     -> waiting
thinking  -> review
sleepy    -> idle
sad       -> failed
```

If the manifest includes `states`, `animations`, or `animationStates`, those row
names are used instead of the inferred/default order. Entries may be plain
strings or objects with `name`, `id`, `key`, `state`, or `slug`. This is how the
loader also accepts explicit Petdex-style 8-row packages such as `idle`, `wave`,
`run`, `failed`, `review`, `jump`, `extra1`, and `extra2`. For Petdex rows,
whether inferred from atlas size or listed explicitly, the default six-frame
loop is spread across exactly 1100ms as `184,184,183,183,183,183 ms` unless the
manifest supplies explicit durations.

## Verify after copying a pet

On an internet-connected staging workstation, download one Petdex pet by slug:

```bash
PYTHONPATH=src python -m coding_pet.cli admin download-petdex boba \
  --output-dir /tmp/downloaded-pets \
  --json-out /tmp/downloaded-pets/boba-download.json
```

The command reads the Petdex manifest API, downloads the pet's ZIP with a
browser-like User-Agent for R2 compatibility, validates the ZIP, and writes
`<slug>.petdex.json` beside `<slug>.zip`. That metadata includes source URLs,
download time, ZIP SHA-256, byte size, and the same validation report produced
by `validate-pet`. Run this only on a workstation that is allowed to reach
Petdex; the target desktop runtime does not download pet files.

Validate a downloaded package before making it active:

```bash
PYTHONPATH=src python -m coding_pet.cli admin validate-pet /path/to/downloaded-pet \
  --json-out /tmp/coding-pet-validation.json
```

`/path/to/downloaded-pet` can be a directory, a `pet.json`, a `petjson.json`, or
a ZIP download.

Expected output includes:

```text
valid_pet=<pet-id>
theme_format=codex_pet
spritesheet=spritesheet.webp
atlas_size=1536x1872
atlas_cells=ok
```

For Petdex-style 8-row packages, `atlas_size=1728x1664` and `atlas_grid=9x8`
are expected when the frame size remains 192x208. This also applies to current
Petdex downloads whose `pet.json` omits explicit state metadata.

The JSON report includes `ok`, `theme_id`, `atlas_size`, `atlas_grid`,
`frame_size`, `frame_counts_by_row`, `frame_durations_by_row`, `mood_rows`, and
`atlas_cells`. Keep this file with the target-host acceptance logs when
importing third-party pets into the intranet.

To check a staging directory full of copied ZIP downloads and extracted package
directories:

```bash
PYTHONPATH=src python -m coding_pet.cli admin validate-pet-batch /path/to/downloaded-pets \
  --json-out /tmp/coding-pet-pet-batch.json
```

The batch report includes `total`, `passed`, `failed`, one validation entry per
package, and exits non-zero if any copied package is invalid. Batch discovery
accepts ZIP files, package directories with `pet.json`, package directories with
`petjson.json`, and standalone `pet.json` or `petjson.json` files. Required
target evidence later checks that those counts still match the accepted package
list. This is the recommended pre-transfer gate when users collect several
Petdex/CodexPets files on an internet-connected workstation before moving them
into the intranet.

When a ZIP has a sibling `<slug>.petdex.json` from `download-petdex`, the batch
report records it as `petdex_metadata` with the sidecar SHA-256, byte size,
source URLs, Petdex slug, and original archive hash. The target evidence gate
checks that `petdex_metadata.archive_sha256` and `archive_size_bytes` still
match the copied ZIP transfer record.

To install a validated staging directory into a Codex-compatible pets root:

```bash
PYTHONPATH=src python -m coding_pet.cli admin import-pet-batch /path/to/downloaded-pets \
  --pets-root ~/.codex/pets \
  --json-out /tmp/coding-pet-pet-import-batch.json
```

`import-pet-batch` validates the full batch first, refuses duplicate pet IDs,
refuses existing targets unless `--replace` is passed, and only starts copying
after those preflight checks pass. The installed layout is
`<pets-root>/<pet-id>/pet.json` plus the package assets, matching the path used
by Codex/Petdex tooling. When the source only has `petjson.json`, the import
keeps that file and writes a `pet.json` alias for compatibility.

To include the same staging directory in the final target evidence bundle:

```bash
PYTHONPATH=src python -m coding_pet.cli admin evidence-bundle \
  --profile target \
  --output-dir /tmp/coding-pet-target-evidence \
  --pet-source /path/to/downloaded-pets \
  --require-pet-packages
```

This writes `pet-packages.json`. The final `target-evidence-check` gate requires
that file to pass when it is marked as required. Each copied package entry also
records transfer metadata: package kind, SHA-256, size in bytes, file count,
source package path, theme id, and manifest path. The gate also rejects
inconsistent `total`, `passed`, `failed`, and `pets` counts. If Petdex sidecar
metadata is present, the gate also rejects missing sidecar hashes, missing
source URLs, or sidecar archive hashes that no longer match the copied ZIP.

Or build the full QA bundle in one step:

```bash
PYTHONPATH=src python -m coding_pet.cli admin build-pet-qa /path/to/downloaded-pet \
  --output-dir /tmp/coding-pet-qa
```

The bundle contains `validation.json`, `contact-sheet.png`,
`animation-previews/*.gif`, and `run-summary.json`.

To install a downloaded package into the configured pets root:

```bash
PYTHONPATH=src python -m coding_pet.cli admin import-pet /path/to/downloaded-pet
```

Use `--pets-root /approved/path/codex-pets` to install somewhere other than
`~/.codex/pets`. ZIP downloads are extracted safely before copying. Existing
package directories are not overwritten unless `--replace` is passed.

Persist the active pet for systemd user services:

```bash
PYTHONPATH=src python -m coding_pet.cli admin set-pet <pet-id>
```

`set-pet` validates the theme before editing `~/.config/coding-pet/service.env`.
It preserves existing comments and unrelated settings, updates
`CODING_PET_THEME`, and writes `CODING_PET_CODEX_PETS_DIR` for imported
Codex/Petdex packages.

List bundled and imported pets:

```bash
PYTHONPATH=src python -m coding_pet.cli admin list-pets
```

Inspect the frame plan that the widget will use:

```bash
PYTHONPATH=src python -m coding_pet.cli admin inspect-pet <pet-id>
```

For a Codex package, this prints the spritesheet path, atlas size, grid, frame
size, fallback frame duration, and each coding-pet mood's source row, frame
count, first crop rectangle, and per-frame durations.

Render a single frame preview PNG when PySide6 is available:

```bash
PYTHONPATH=src python -m coding_pet.cli admin render-pet-frame <pet-id> \
  --mood alert \
  --output /tmp/coding-pet-preview.png
```

Render a full atlas contact sheet for visual QA:

```bash
PYTHONPATH=src python -m coding_pet.cli admin render-pet-contact-sheet <pet-id> \
  --output /tmp/coding-pet-contact-sheet.png
```

The contact sheet is Pillow-based and can run in headless environments. It
labels rows, marks used frames with a blue outline, and marks unused cells with
a red diagonal so transparent unused cells can be inspected quickly.

Render motion preview GIFs for every atlas row:

```bash
PYTHONPATH=src python -m coding_pet.cli admin render-pet-animation-previews <pet-id> \
  --output-dir /tmp/coding-pet-previews
```

The GIF previews are also Pillow-based and use each row's frame durations for
official Codex-layout atlases. They should be kept with the validation JSON and
contact sheet when a copied pet is reviewed for approval.

Then verify the selected pet:

```bash
CODING_PET_THEME=<pet-id> PYTHONPATH=src python -m coding_pet.cli admin doctor
CODING_PET_THEME=<pet-id> PYTHONPATH=src python -m coding_pet.cli widget run
```

Expected doctor output:

```text
configured_theme=<pet-id>
theme=<pet-id>
theme_format=codex_pet
theme_missing_assets=none
```

## Notes

- `assets/sprites/codex-default` remains only the built-in fallback.
- The app does not download pet files at runtime.
- `validate-pet` rejects missing spritesheets, unsafe relative paths, symlinks,
  unsafe ZIP entries, unsupported spritesheet extensions, PNG/WebP files whose
  header dimensions do not match the manifest layout, package IDs that cannot
  be used as a safe local directory name, and spritesheets that violate the
  official atlas cell contract. Used cells must contain visible pixels, unused
  cells after each row's frame count must be transparent, the file must expose
  an alpha channel, and nearly opaque used cells are rejected because they
  usually indicate a non-transparent background.
- Fully transparent pixels with non-zero RGB residue are reported as warnings,
  not failures. Some real WebP pet packages preserve RGB data under alpha-zero
  pixels even though they still render transparent.
- External pet licenses and redistribution rights are a company/user
  responsibility when files are copied into the intranet.
