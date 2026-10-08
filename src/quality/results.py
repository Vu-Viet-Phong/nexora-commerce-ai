"""Small, JSON-safe validation results; reports contain aggregate data only."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Literal

Status = Literal["PASS", "FAIL", "SKIP"]


@dataclass(frozen=True)
class ValidationResult:
    name: str
    expected: Any
    actual: Any
    status: Status
    execution_ms: float = 0.0
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in ("PASS", "FAIL", "SKIP"):
            raise ValueError("status must be PASS, FAIL, or SKIP")


def compare(
    name: str, expected: Any, actual: Any, *, execution_ms: float = 0.0,
    tolerance: Decimal | None = None,
) -> ValidationResult:
    """Compare aggregates, using explicit decimal tolerance when requested."""
    if tolerance is not None:
        if tolerance < 0:
            raise ValueError("tolerance must be non-negative")
        passed = abs(Decimal(str(actual)) - Decimal(str(expected))) <= tolerance
    else:
        passed = expected == actual
    return ValidationResult(
        name, expected, actual, "PASS" if passed else "FAIL", execution_ms,
        None if passed else "Aggregate does not match the approved contract.",
    )


def skipped(name: str, reason: str) -> ValidationResult:
    return ValidationResult(name, None, None, "SKIP", failure_reason=reason)


@dataclass
class QualityReport:
    source_system: str
    schema: str
    results: list[ValidationResult] = field(default_factory=list)
    execution_ms: float = 0.0
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def summary(self) -> dict[str, Any]:
        counts = Counter(result.status for result in self.results)
        # SKIP means incomplete coverage, never a green quality gate.
        status = "FAIL" if counts["FAIL"] else ("SKIP" if counts["SKIP"] else "PASS")
        return {"status": status, "total": len(self.results),
                **{key: counts[key] for key in ("PASS", "FAIL", "SKIP")}}

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "summary": self.summary}

    def to_json(self) -> str:
        def encode(value: Any) -> str:
            if isinstance(value, Decimal):
                return format(value, "f")
            raise TypeError(f"Unsupported report value type: {type(value).__name__}")
        return json.dumps(self.as_dict(), ensure_ascii=False, indent=2, default=encode)

    def to_markdown(self) -> str:
        def cell(value: Any) -> str:
            if value is None:
                return "—"
            return str(value).replace("|", "\\|").replace("\n", " ")
        rows = [
            "# Nexora data quality report",
            "",
            f"Overall: {self.summary['status']}; checks: {self.summary['total']}; "
            f"PASS: {self.summary['PASS']}; FAIL: {self.summary['FAIL']}; "
            f"SKIP: {self.summary['SKIP']}; runtime: {self.execution_ms:.2f} ms.",
            "",
            "| Validation | Expected | Actual | Status | ms | Reason |",
            "|---|---|---|---|---:|---|",
        ]
        for result in self.results:
            rows.append("| " + " | ".join(map(cell, (
                result.name, result.expected, result.actual, result.status,
                f"{result.execution_ms:.2f}", result.failure_reason,
            ))) + " |")
        return "\n".join(rows) + "\n"

    def write(self, path: Path, *, markdown: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown() if markdown else self.to_json(),
                        encoding="utf-8")
