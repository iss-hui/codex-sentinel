from pathlib import Path
from codex_sentinel.lock_manager import is_lock_free, wait_for_lock_release


def test_is_lock_free_non_existent(tmp_path: Path):
    non_existent = tmp_path / "not_there.lock"
    assert is_lock_free(non_existent) is True


def test_is_lock_free_empty_file(tmp_path: Path):
    lock_file = tmp_path / "test.lock"
    lock_file.touch()
    assert is_lock_free(lock_file) is True


def test_wait_for_lock_release_empty_session():
    # Empty session string should safely return True
    assert wait_for_lock_release("", timeout=0.1) is True
