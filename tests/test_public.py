"""Public tests for the download path confinement module."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from safepath import normalize, path_batch, safe_join


def _make_dir_link(link: Path, target: Path) -> None:
    """Create a directory link, using a junction when symlinks are unavailable."""

    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        pass

    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"could not create directory link {link} -> {target}")


def test_normal_relative_path_passes(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    user_path = "reports/./2026/q1.txt"
    assert normalize(user_path) == "reports/2026/q1.txt"

    resolved = safe_join(str(root), user_path)
    assert Path(resolved) == root / "reports" / "2026" / "q1.txt"


def test_parent_traversal_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ValueError):
        safe_join(str(root), "../../etc/passwd")


def test_absolute_path_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = root / "private" / "config.ini"

    with pytest.raises(ValueError):
        safe_join(str(root), str(target))


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")

    _make_dir_link(root / "link", outside)

    with pytest.raises(ValueError):
        safe_join(str(root), "link/secret.txt")


def test_batch_keeps_paths_independent(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    results = path_batch(str(root), ["docs/good.txt", "../../etc/passwd"])

    assert results["docs/good.txt"]["ok"] is True
    assert results["../../etc/passwd"]["ok"] is False