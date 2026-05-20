# GUI asset notes

Runtime sprite themes live under the repository-level `assets/sprites/` tree and are discovered through `coding_pet.gui.theme`. Installed wheels also expose them as shared data under `share/coding-pet/assets/sprites/`; `CODING_PET_ASSETS_DIR` can point at an approved override root.

The default checked-in theme is `assets/sprites/company-pet/`, with `assets/sprites/classic/` retained as the text fallback theme.

Additional selectable sample characters from PMD SpriteCollab are registered in `assets/sprites/theme-registry.json` and live under `assets/sprites/pmd-*`. These are CC BY-NC 4.0 sample assets with preserved per-character credits; do not treat them as company-owned production art.

This package-local directory is reserved for future GUI-specific static files that need to live inside the Python package itself.
