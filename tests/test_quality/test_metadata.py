from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest

from src.quality.metadata import (
    FOREIGN_KEYS, INDEXES, PRIMARY_KEYS, UNIQUE_KEYS, metadata_results, validate_metadata,
)


def enforcement_catalog(schema="public"):
    constraints = []
    for table, cols in PRIMARY_KEYS.items():
        constraints.append(dict(table_name=table, kind="p", columns=list(cols),
                                validated=True, index_valid=True, index_ready=True))
    for table, keys in UNIQUE_KEYS.items():
        for cols in keys:
            constraints.append(dict(table_name=table, kind="u", columns=list(cols),
                                    validated=True, index_valid=True, index_ready=True))
    for table, cols, parent, parent_cols in FOREIGN_KEYS:
        constraints.append(dict(table_name=table, kind="f", columns=list(cols),
                                referenced_schema=schema, referenced_table=parent,
                                referenced_columns=list(parent_cols), delete_action="r",
                                update_action="a", validated=True, index_valid=True, index_ready=True))
    indexes = [
        dict(table_name=table, index_name=name, columns=list(cols), method="btree",
             is_unique=False, valid=True, ready=True, unconditional_simple=True)
        for (table, name), cols in INDEXES.items()
    ]
    return constraints, indexes


def test_enforcement_matches_accepted_ddl():
    assert all(r.status == "PASS" for r in metadata_results(*enforcement_catalog(), "public"))


@pytest.mark.parametrize("kind,name", [
    ("p", "schema.primary_keys"), ("f", "schema.foreign_keys"), ("u", "schema.unique_constraints"),
])
def test_missing_constraints_fail_with_clean_data(kind, name):
    constraints, indexes = enforcement_catalog()
    constraints.remove(next(r for r in constraints if r["kind"] == kind))
    results = {r.name: r for r in metadata_results(constraints, indexes, "public")}
    assert results[name].actual["missing"] == 1


@pytest.mark.parametrize("field,value", [
    ("referenced_schema", "other_schema"), ("referenced_table", "products"),
    ("referenced_columns", ["customer_id", "source_system"]), ("delete_action", "c"),
    ("update_action", "c"), ("validated", False), ("index_valid", False),
])
def test_fk_wrong_target_or_enforcement_is_invalid(field, value):
    constraints, indexes = enforcement_catalog()
    next(r for r in constraints if r["kind"] == "f")[field] = value
    results = {r.name: r for r in metadata_results(constraints, indexes, "public")}
    assert results["schema.foreign_keys"].actual["invalid"] == 1


@pytest.mark.parametrize("field,value", [
    ("columns", ["invoice_date", "source_system"]), ("method", "hash"),
    ("valid", False), ("ready", False), ("unconditional_simple", False), ("is_unique", True),
])
def test_index_definition_and_validity_not_just_name(field, value):
    constraints, indexes = enforcement_catalog()
    indexes[0][field] = value
    assert metadata_results(constraints, indexes, "public")[-1].actual["invalid"] == 1


def test_missing_index_is_reported():
    constraints, indexes = enforcement_catalog()
    indexes.pop()
    assert metadata_results(constraints, indexes, "public")[-1].actual["missing"] == 1


def test_catalog_errors_fail_safely_and_use_savepoint():
    connection = MagicMock()
    connection.begin_nested.return_value = nullcontext()
    connection.execute.side_effect = RuntimeError("sentinel-sensitive-value")
    results = validate_metadata(connection, "public")
    assert len(results) == 4 and all(r.status == "FAIL" for r in results)
    assert "sentinel-sensitive-value" not in str(results)
    connection.begin_nested.assert_called_once()
