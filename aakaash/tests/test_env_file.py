# SOURCE: NOT IN PAPERS. Uses a temporary .env with a fake value.
from api.config import load_env_file

NAME = "LLM_API_KEY"


def test_file_value_is_loaded(tmp_path, monkeypatch):
    monkeypatch.delenv(NAME, raising=False)
    f = tmp_path / ".env"
    f.write_text(f"{NAME}=fake-from-file\n", encoding="utf-8")
    try:
        assert load_env_file(f) is True
        import os
        assert os.environ[NAME] == "fake-from-file"
    finally:
        monkeypatch.delenv(NAME, raising=False)


def test_real_environment_wins(tmp_path, monkeypatch):
    monkeypatch.setenv(NAME, "fake-from-env")
    f = tmp_path / ".env"
    f.write_text(f"{NAME}=fake-from-file\n", encoding="utf-8")
    load_env_file(f)
    import os
    assert os.environ[NAME] == "fake-from-env"


def test_missing_file_does_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv(NAME, raising=False)
    assert load_env_file(tmp_path / "absent.env") is False
    import os
    assert NAME not in os.environ
