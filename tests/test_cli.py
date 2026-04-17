from __future__ import annotations

import pytest
from typer.testing import CliRunner

from coding_pet.cli import app

runner = CliRunner()


@pytest.mark.parametrize(
    ("args", "expected_fragment"),
    [
        (["daemon", "run"], "not implemented"),
        (["widget", "run"], "not implemented"),
        (["admin", "doctor"], "not implemented"),
    ],
)
def test_placeholder_commands_fail_until_implemented(
    args: list[str],
    expected_fragment: str,
) -> None:
    result = runner.invoke(app, args)

    assert result.exit_code != 0
    assert expected_fragment in result.stdout.lower()
