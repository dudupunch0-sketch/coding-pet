from __future__ import annotations

import asyncio
import sys
from pathlib import Path


async def _main() -> None:
    from coding_pet.cli import _serve_daemon_runtime

    await _serve_daemon_runtime(oneshot=False)


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
