import os

import pytest

from . import full_data_probe as probe
from .test_source import make_source


@pytest.mark.parametrize("url", [None, "invalid sensitive sentinel", "sqlite:///local.db",
                               "postgresql://qa@localhost/shared_database"])
def test_probe_rejects_missing_invalid_or_shared_configuration(monkeypatch, tmp_path, capsys, url):
    if url is None:
        monkeypatch.delenv("NEXORA_QUALITY_TEST_DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("NEXORA_QUALITY_TEST_DATABASE_URL", url)
    def unexpected(*args, **kwargs):
        pytest.fail("Must reject configuration before connecting")
    monkeypatch.setattr(probe, "create_engine", unexpected)
    with pytest.raises(SystemExit) as error:
        probe.main(["--phase", "validate", "--source", str(tmp_path / "absent.parquet"),
                    "--schema", "codex_quality_full_fixture", "--output-dir", str(tmp_path / "out")])
    assert error.value.code == 2
    assert "sensitive sentinel" not in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_probe_requires_exact_full_source_before_connecting(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXORA_QUALITY_TEST_DATABASE_URL",
                       "postgresql://qa@localhost/nexora_quality_codex_test")
    source = make_source(tmp_path)
    def unexpected(*args, **kwargs):
        pytest.fail("Must reject incomplete source before connecting")
    monkeypatch.setattr(probe, "create_engine", unexpected)
    with pytest.raises(SystemExit) as error:
        probe.main(["--phase", "load", "--source", str(source),
                    "--schema", "codex_quality_full_fixture", "--output-dir", str(tmp_path / "out")])
    assert error.value.code == 2
    assert not (tmp_path / "out").exists()


def test_probe_requires_owned_schema(tmp_path):
    with pytest.raises(SystemExit) as error:
        probe.main(["--phase", "load", "--source", str(tmp_path / "absent.parquet"),
                    "--schema", "public", "--output-dir", str(tmp_path / "out")])
    assert error.value.code == 2


def test_peak_memory_reports_native_or_explicit_unavailable():
    memory = probe.peak_memory()
    if os.name == "nt":
        assert memory["peak_working_set_bytes"] > 0
        assert memory["peak_commit_bytes"] > 0
    else:
        assert memory["method"] == "unavailable"
        assert memory["peak_working_set_bytes"] is None
        assert memory["peak_commit_bytes"] is None
