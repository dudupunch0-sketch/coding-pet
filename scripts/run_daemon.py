from __future__ import annotations

import asyncio
import sys
from pathlib import Path


async def _main() -> None:
    from coding_pet.config import load_config
    from coding_pet.daemon.app import DaemonApp
    from coding_pet.state_store import StateStore

    config = load_config()
    config.runtime_dir.mkdir(parents=True, exist_ok=True)
    _daemon = DaemonApp()
    _state_store = StateStore(config.state_file)
    print(
        (
            "coding-pet daemon placeholder ready; "
            f"runtime_dir={config.runtime_dir} state_file={config.state_file}"
        ),
        flush=True,
    )
    await asyncio.Event().wait()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        print("coding-pet daemon stopped")


if __name__ == "__main__":
    main()
