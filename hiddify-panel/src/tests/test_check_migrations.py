import importlib.util, pathlib, tempfile, os

_ROOT = pathlib.Path(__file__).resolve().parents[3]  # repo root
_spec = importlib.util.spec_from_file_location(
    "check_migrations", _ROOT / "common" / "check_migrations.py")
cm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cm)

def _write(tmp_path, body: str) -> str:
    p = tmp_path / "init_db.py"
    p.write_text(body)
    return str(p)

def test_clean_file_passes(tmp_path):
    body = "MAX_DB_VERSION = 2\ndef _v1():\n    pass\ndef _v2():\n    pass\n"
    assert cm.check_file(_write(tmp_path, body)) is True

def test_duplicate_vnnn_fails(tmp_path):
    body = "MAX_DB_VERSION = 2\ndef _v1():\n    pass\ndef _v1():\n    pass\n"
    assert cm.check_file(_write(tmp_path, body)) is False

def test_max_db_version_lower_than_highest_vnnn_fails(tmp_path):
    body = "MAX_DB_VERSION = 1\ndef _v1():\n    pass\ndef _v2():\n    pass\n"
    assert cm.check_file(_write(tmp_path, body)) is False
