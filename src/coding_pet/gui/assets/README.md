# GUI asset notes

Runtime sprite themes currently live under the repository-level `assets/sprites/` tree and are discovered through `coding_pet.gui.theme`. Installed wheels also expose them as shared data under `share/coding-pet/assets/sprites/`; `CODING_PET_ASSETS_DIR` can point at an approved override root.

The default checked-in theme is `assets/sprites/company-pet/`, with `assets/sprites/classic/` retained as the text fallback theme.

This package-local directory is reserved for future GUI-specific static files that need to live inside the Python package itself.
