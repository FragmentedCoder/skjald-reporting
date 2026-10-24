import multiprocessing

from app.crypto.key_files import load_or_create_database_key
from app.crypto.keys import generate_key


def _write_master_key(directory):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "master.key"
    path.write_bytes(generate_key())
    return path


def test_creates_and_persists_a_wrapped_key(tmp_path) -> None:
    master_key_path = _write_master_key(tmp_path)
    data_dir = tmp_path / "data"

    key = load_or_create_database_key(data_dir, master_key_path)

    assert len(key) == 32
    assert (data_dir / "db.key.enc").exists()
    assert (data_dir / "db.key.enc").stat().st_mode & 0o777 == 0o600


def test_returns_the_same_key_on_a_second_call(tmp_path) -> None:
    master_key_path = _write_master_key(tmp_path)
    data_dir = tmp_path / "data"

    first = load_or_create_database_key(data_dir, master_key_path)
    second = load_or_create_database_key(data_dir, master_key_path)

    assert first == second


def test_different_installs_get_different_keys(tmp_path) -> None:
    key_a = load_or_create_database_key(tmp_path / "a", _write_master_key(tmp_path / "a-etc"))
    key_b = load_or_create_database_key(tmp_path / "b", _write_master_key(tmp_path / "b-etc"))
    assert key_a != key_b


def test_processes_starting_at_once_all_get_the_same_key(tmp_path) -> None:
    master_key_path = _write_master_key(tmp_path)
    data_dir = tmp_path / "data"

    with multiprocessing.get_context("spawn").Pool(8) as pool:
        keys = pool.starmap(load_or_create_database_key, [(data_dir, master_key_path)] * 8)

    assert len(set(keys)) == 1
    assert not list(data_dir.glob(".*.tmp"))
