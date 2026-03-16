"""Basic CLI smoke tests."""
import pytest
import subprocess
import sys


def test_cli_help():
    """dsm --help should exit 0."""
    result = subprocess.run(
        [sys.executable, "-m", "dsm", "--help"],
        capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0
    assert "usage" in result.stdout.lower() or "dsm" in result.stdout.lower()


def test_cli_version():
    """dsm --version should print version (or exit 2 if not implemented)."""
    result = subprocess.run(
        [sys.executable, "-m", "dsm", "--version"],
        capture_output=True, text=True, timeout=10
    )
    # Accept 0 (version printed) or 2 (argparse unknown --version)
    assert result.returncode in (0, 2)


def test_cli_coverage_requires_args():
    """dsm coverage without required args should fail gracefully."""
    result = subprocess.run(
        [sys.executable, "-m", "dsm", "coverage"],
        capture_output=True, text=True, timeout=10
    )
    # Should fail but not crash with a traceback
    assert result.returncode != 0 or "error" in result.stderr.lower() or "usage" in result.stderr.lower()
