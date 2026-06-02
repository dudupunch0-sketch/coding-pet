from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_and_rhel8_constraints_keep_pyside6_on_manylinux_2_28_range() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    constraints = (ROOT / "requirements" / "constraints-rhel8.txt").read_text("utf-8")
    runtime = (ROOT / "requirements" / "rhel8-runtime.txt").read_text("utf-8")
    dev = (ROOT / "requirements" / "rhel8-dev.txt").read_text("utf-8")

    pyside_range = "PySide6>=6.8,<6.10"
    pillow_range = "Pillow>=11,<13"

    assert pyproject["project"]["requires-python"] == ">=3.12,<3.13"
    assert pillow_range in pyproject["project"]["dependencies"]
    assert pyside_range in pyproject["project"]["optional-dependencies"]["gui"]
    assert pyside_range in pyproject["project"]["optional-dependencies"]["dev"]
    assert pillow_range in constraints
    assert pyside_range in constraints
    assert "PySide6>=6.10" not in constraints
    assert "-c constraints-rhel8.txt" in runtime
    assert "Pillow" in runtime
    assert "PySide6" in runtime
    assert "-r rhel8-runtime.txt" in dev


def test_offline_wheelhouse_docs_target_rhel8_glibc_and_cross_platform_tags() -> None:
    guide = (ROOT / "docs" / "operations" / "offline-rhel8-wheelhouse.md").read_text("utf-8")

    assert "RHEL 8.10" in guide
    assert "glibc 2.28" in guide
    assert "--platform manylinux_2_28_x86_64" in guide
    assert "--python-version 312" in guide
    assert "--abi cp312" in guide
    assert "--abi abi3" in guide
    assert "--abi none" in guide
    assert "PySide6 below 6.10" in guide
    assert "Pillow" in guide
    assert "manylinux_2_34" in guide
