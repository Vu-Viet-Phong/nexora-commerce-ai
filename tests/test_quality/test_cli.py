import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import src.quality.__main__ as cli
from src.quality.results import QualityReport, compare, skipped


def success():
    return QualityReport("UCI", "public", [
        compare("schema.required_columns", [], []), compare("source.records", 0, 0),
        skipped("marts.mart_daily_sales", "Pending 2.4"),
    ])


def test_unconfigured_environment_exits_fail_without_env_file(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert cli.main([]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["FAIL"] == 1


def test_cli_outputs_both_reports_and_disposes_engine(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://qa@localhost:5432/quality")
    engine = MagicMock()
    monkeypatch.setattr(cli, "create_engine", lambda *a, **kw: engine)
    monkeypatch.setattr(cli, "validate_database", lambda *a, **kw: success())
    json_file, md_file = tmp_path / "quality.json", tmp_path / "quality.md"
    assert cli.main(["--json-out", str(json_file), "--markdown-out", str(md_file)]) == 0
    stdout = json.loads(capsys.readouterr().out)
    assert stdout == json.loads(json_file.read_text(encoding="utf-8"))
    assert stdout["summary"]["status"] == "SKIP"  # Marts coverage is still pending.
    assert stdout["gate_summary"]["status"] == "PASS"
    assert "PASS" in md_file.read_text(encoding="utf-8")
    engine.dispose.assert_called_once()


def test_skipped_source_is_incomplete_gate(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://qa@localhost:5432/quality")
    monkeypatch.setattr(cli, "create_engine", lambda *a, **kw: MagicMock())
    report = success()
    report.results.append(skipped("source.reconciliation", "No source supplied"))
    monkeypatch.setattr(cli, "validate_database", lambda *a, **kw: report)
    assert cli.main([]) == 2
    assert json.loads(capsys.readouterr().out)["gate_summary"]["status"] == "SKIP"


def test_connection_errors_never_print_exception_content(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://qa@localhost:5432/quality")

    def broken(*args, **kwargs):
        raise RuntimeError("sentinel-sensitive-value")

    monkeypatch.setattr(cli, "create_engine", broken)
    assert cli.main([]) == 1
    assert "sentinel-sensitive-value" not in capsys.readouterr().out


@pytest.mark.parametrize("url", ["not a URL", "sqlite:///local.db"])
def test_invalid_database_configuration_fails_safely(monkeypatch, capsys, url):
    monkeypatch.setenv("DATABASE_URL", url)
    assert cli.main([]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["results"][0]["name"] == "database.connection"


@pytest.mark.parametrize("arguments", [
    ["--schema", "x; DROP TABLE customers"], ["--statement-timeout-ms", "0"],
    ["--source-system", ""], ["--json-out", "same.json", "--markdown-out", "same.json"],
])
def test_invalid_options_exit_before_connecting(monkeypatch, arguments):
    engine = MagicMock()
    monkeypatch.setattr(cli, "create_engine", engine)
    with pytest.raises(SystemExit) as exit_error:
        cli.main(arguments)
    assert exit_error.value.code == 2
    engine.assert_not_called()


def test_output_error_is_failure_and_sanitized(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://qa@localhost:5432/quality")
    monkeypatch.setattr(cli, "create_engine", lambda *a, **kw: MagicMock())
    monkeypatch.setattr(cli, "validate_database", lambda *a, **kw: success())
    assert cli.main(["--json-out", str(tmp_path)]) == 1  # Cannot write over a directory.
    report = json.loads(capsys.readouterr().out)
    assert report["results"][-1]["name"] == "report.output"


def test_empty_report_is_not_a_green_gate():
    report = QualityReport("UCI", "public")
    assert report.summary["status"] == "SKIP"
    assert report.gate_summary["status"] == "SKIP"
