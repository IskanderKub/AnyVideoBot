import time
from pathlib import Path

from app.services.cleanup import remove_path, sweep_temp_dir


def test_remove_path_deletes_file_and_dir(tmp_path: Path):
    file_path = tmp_path / "video.mp4"
    file_path.write_bytes(b"data")
    nested = tmp_path / "job" / "inner"
    nested.mkdir(parents=True)
    (nested / "part.mp4").write_bytes(b"data")

    remove_path(file_path)
    remove_path(tmp_path / "job")

    assert not file_path.exists()
    assert not (tmp_path / "job").exists()


def test_remove_path_is_silent_on_missing(tmp_path: Path):
    remove_path(tmp_path / "nope.mp4")
    remove_path(None)


def test_sweep_removes_only_stale_entries(tmp_path: Path):
    fresh = tmp_path / "fresh.mp4"
    fresh.write_bytes(b"x")
    stale = tmp_path / "stale.mp4"
    stale.write_bytes(b"x")
    old = time.time() - 7200
    import os

    os.utime(stale, (old, old))

    removed = sweep_temp_dir(root=tmp_path, max_age_sec=3600)

    assert removed == 1
    assert fresh.exists()
    assert not stale.exists()


def test_sweep_on_missing_dir_returns_zero(tmp_path: Path):
    assert sweep_temp_dir(root=tmp_path / "absent", max_age_sec=0) == 0


def test_ensure_writable_passes_on_a_normal_dir(tmp_path: Path):
    from app.services.cleanup import ensure_temp_dir_writable

    assert ensure_temp_dir_writable(tmp_path / "temp") == tmp_path / "temp"
    # The probe must not be left behind.
    assert list((tmp_path / "temp").iterdir()) == []


def test_ensure_writable_raises_on_a_read_only_dir(tmp_path: Path):
    """A root-owned tmpfs mount looks exactly like this to a non-root process."""
    import os

    import pytest

    from app.services.cleanup import ensure_temp_dir_writable

    if os.geteuid() == 0:
        pytest.skip("root ignores directory permissions")

    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    try:
        with pytest.raises(RuntimeError, match="not writable"):
            ensure_temp_dir_writable(locked)
    finally:
        locked.chmod(0o755)
