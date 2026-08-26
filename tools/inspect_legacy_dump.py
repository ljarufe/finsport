#!/usr/bin/env python3
"""Inspect selected non-sensitive COPY data in a plain-text legacy pg_dump.

This utility parses text only. It never connects to PostgreSQL and never executes SQL.
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

SAFE_DATA_TABLES = {
    "football_league",
    "football_leaguerelatedname",
    "football_team",
    "football_match",
    "bet_bettable",
    "bet_betrow",
}
COPY_PATTERN = re.compile(r'^COPY (?:public\.)?"?([^" (]+)"? \(([^)]+)\) FROM stdin;$')
CREATE_PATTERN = re.compile(r'^CREATE TABLE (?:public\.)?"?([^" (]+)"? \($')


def inspect_dump(path):
    report = {
        "format": "plain-text pg_dump metadata (no SQL executed)",
        "tables": {
            table: {"copy_columns": [], "row_count": 0, "present": False}
            for table in sorted(SAFE_DATA_TABLES)
        },
        "migration_names": {"football": [], "bet": []},
        "research": {},
        "ignored_copy_sections": 0,
    }
    current_table = None
    current_columns = []
    current_safe = False
    rows = []
    schema_tables = set()

    with Path(path).open(encoding="utf-8", errors="replace") as dump:
        for raw_line in dump:
            line = raw_line.rstrip("\n")
            if current_table:
                if line == r"\.":
                    if current_safe:
                        _summarize_copy(report, current_table, current_columns, rows)
                    current_table = None
                    current_columns = []
                    current_safe = False
                    rows = []
                elif current_safe:
                    rows.append(line.split("\t"))
                continue

            create_match = CREATE_PATTERN.match(line)
            if create_match and _is_safe_table(create_match.group(1)):
                schema_tables.add(create_match.group(1))

            copy_match = COPY_PATTERN.match(line)
            if not copy_match:
                continue
            current_table = copy_match.group(1)
            current_columns = [
                column.strip().strip('"') for column in copy_match.group(2).split(",")
            ]
            current_safe = (
                _is_safe_table(current_table) or current_table == "django_migrations"
            )
            if not current_safe:
                report["ignored_copy_sections"] += 1

    report["schema_tables"] = sorted(schema_tables)
    return report


def _is_safe_table(table):
    return table in SAFE_DATA_TABLES


def _summarize_copy(report, table, columns, rows):
    if table == "django_migrations":
        _summarize_migrations(report, columns, rows)
        return
    report["tables"][table] = {
        "copy_columns": columns,
        "row_count": len(rows),
        "present": True,
    }
    if table == "bet_betrow":
        states = _count_column(columns, rows, "state")
        iterations = _integer_column(columns, rows, "iteration")
        report["research"]["bet_betrow_states"] = states
        report["research"]["bet_betrow_max_iteration"] = (
            max(iterations) if iterations else None
        )
    elif table == "football_match":
        states = _count_column(columns, rows, "state")
        if states:
            report["research"]["football_match_states"] = states


def _summarize_migrations(report, columns, rows):
    try:
        app_index = columns.index("app")
        name_index = columns.index("name")
    except ValueError:
        return
    for row in rows:
        if len(row) <= max(app_index, name_index):
            continue
        app = row[app_index]
        if app in report["migration_names"]:
            report["migration_names"][app].append(row[name_index])


def _count_column(columns, rows, name):
    try:
        index = columns.index(name)
    except ValueError:
        return {}
    return dict(sorted(Counter(row[index] for row in rows if len(row) > index).items()))


def _integer_column(columns, rows, name):
    try:
        index = columns.index(name)
    except ValueError:
        return []
    values = []
    for row in rows:
        if len(row) <= index:
            continue
        try:
            values.append(int(row[index]))
        except ValueError:
            continue
    return values


def main():
    parser = argparse.ArgumentParser(
        description="Safely summarize selected legacy Finsport pg_dump data."
    )
    parser.add_argument("dump", type=Path, help="External plain-text pg_dump path")
    arguments = parser.parse_args()
    print(json.dumps(inspect_dump(arguments.dump), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
