import pytest

from app.config import V1_ROOT
from scripts import verify_v1


@pytest.mark.skipif(not (V1_ROOT / "main.py").exists(), reason="V1 files are not next to v2/")
def test_v1_files_are_byte_identical_to_the_recorded_baseline():
    ok, bad, _ = verify_v1.check()
    assert bad == [] and len(ok) == 7, bad


def test_detects_modification_and_missing_files(tmp_path):
    (tmp_path / "a.py").write_text("print(1)")
    import hashlib
    h = hashlib.sha256(b"print(1)").hexdigest()
    base = tmp_path / "base.sha256"
    base.write_text(f"{h}  ./a.py\n{h}  ./gone.py\n")
    ok, bad, _ = verify_v1.check(tmp_path, base)
    assert ok == ["a.py"] and bad == ["MISSING   gone.py"]
    (tmp_path / "a.py").write_text("print(2)")
    assert verify_v1.check(tmp_path, base)[1][0] == "MODIFIED  a.py"


def test_runtime_artifacts_do_not_count_as_failures(tmp_path):
    (tmp_path / "employee_data.db").write_bytes(b"x"); (tmp_path / "exports").mkdir()
    base = tmp_path / "b.sha256"; base.write_text("")
    ok, bad, present = verify_v1.check(tmp_path, base)
    assert bad == [] and present == ["employee_data.db", "exports"]
