"""KQL query engine — executes queries against in-memory data."""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sdk.repositories import AuditRepository, SqlMachineRepository

from core.adapters import audit_log_to_dict, machine_to_dict
from core.deps import AuditRepositoryWrapper


class KqlEngine:
    """Parse and execute KQL queries against SQLModel repositories."""

    def __init__(
        self,
        machine_repo: SqlMachineRepository,
        audit_repo: AuditRepositoryWrapper,
    ) -> None:
        self.machine_repo = machine_repo
        self.audit_repo = audit_repo

    def execute(self, query: str) -> dict[str, Any]:
        """Execute KQL query and return results."""
        query = query.strip()
        if not query:
            return {"error": "Empty query", "columns": [], "rows": []}

        try:
            # Parse table name and pipeline operators
            # Handle both "Table | op" and "Table\n| op" formats
            parts = query.split("|")
            table_name = parts[0].strip().split("\n")[0].strip()
            
            # Reconstruct pipeline operators
            pipeline = []
            if len(parts) > 1:
                # First operator might be on same line as table
                first_op = parts[0].split("\n", 1)[-1].strip() if "\n" in parts[0] else ""
                if first_op:
                    pipeline.append("|" + first_op)
                # Add remaining operators
                pipeline.extend(["|" + p.strip() for p in parts[1:]])
            
            # Get source data - convert SQLModel objects to dicts
            if table_name.lower() == "auditlog":
                audit_rows = self.audit_repo.list_all()
                data = [audit_log_to_dict(row) for row in audit_rows]
                schema = ["id", "ts", "actor", "action", "machine_id", "result", "detail", "source_ip"]
            elif table_name.lower() == "machines":
                machine_rows = self.machine_repo.list_all()
                data = [machine_to_dict(row) for row in machine_rows]
                schema = list(data[0].keys()) if data else []
            else:
                return {"error": f"Unknown table: {table_name}", "columns": [], "rows": []}

            # Apply pipeline operators
            for op in pipeline:
                data, schema = self._apply_operator(op, data, schema)

            return {"columns": schema, "rows": data, "count": len(data)}

        except Exception as e:
            return {"error": str(e), "columns": [], "rows": []}

    def _apply_operator(
        self, line: str, data: list[dict], schema: list[str]
    ) -> tuple[list[dict], list[str]]:
        """Apply a single KQL operator to the dataset."""
        line = line[1:].strip()  # Remove leading "|"

        # | where <condition>
        if line.startswith("where "):
            condition = line[6:]
            data = [row for row in data if self._eval_where(condition, row)]
            return data, schema

        # | project <col1>, <col2>, ...
        if line.startswith("project "):
            cols = [c.strip() for c in line[8:].split(",")]
            data = [{col: row.get(col) for col in cols} for row in data]
            return data, cols

        # | top <n> by <col> [asc|desc]
        if line.startswith("top "):
            match = re.match(r"top (\d+) by (\w+)(?: (asc|desc))?", line)
            if match:
                n, col, order = match.groups()
                n = int(n)
                reverse = order != "asc"
                data = sorted(data, key=lambda x: x.get(col, ""), reverse=reverse)[:n]
            return data, schema

        # | sort by <col> [asc|desc]
        if line.startswith("sort by "):
            match = re.match(r"sort by (\w+)(?: (asc|desc))?", line)
            if match:
                col, order = match.groups()
                reverse = order == "desc"
                data = sorted(data, key=lambda x: x.get(col, ""), reverse=reverse)
            return data, schema

        # | summarize count() by <col1>, <col2>, ...
        if line.startswith("summarize "):
            # Simple count() by group
            match = re.match(r"summarize count\(\) by (.+)", line)
            if match:
                group_cols = [c.strip() for c in match.group(1).split(",")]
                groups: dict[tuple, int] = {}
                for row in data:
                    key = tuple(row.get(col) for col in group_cols)
                    groups[key] = groups.get(key, 0) + 1
                
                data = [
                    {**dict(zip(group_cols, key)), "count": count}
                    for key, count in groups.items()
                ]
                return data, group_cols + ["count"]

        # | distinct <col>
        if line.startswith("distinct "):
            col = line[9:].strip()
            seen = set()
            unique = []
            for row in data:
                val = row.get(col)
                if val not in seen:
                    seen.add(val)
                    unique.append(row)
            return unique, schema

        # | take <n>
        if line.startswith("take "):
            n = int(line[5:])
            return data[:n], schema

        return data, schema

    def _eval_where(self, condition: str, row: dict) -> bool:
        """Evaluate a where condition against a row."""
        # Handle ago() time expressions
        if "ago(" in condition:
            match = re.search(r"ago\((\d+)([smhd])\)", condition)
            if match:
                value, unit = match.groups()
                value = int(value)
                units = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
                delta = timedelta(**{units[unit]: value})
                threshold = datetime.now(timezone.utc) - delta
                
                # Extract column name and operator
                col_match = re.match(r"(\w+)\s*([><=!]+)\s*ago", condition)
                if col_match:
                    col, op = col_match.groups()
                    row_time = self._parse_timestamp(row.get(col))
                    if row_time:
                        if op == ">":
                            return row_time > threshold
                        elif op == ">=":
                            return row_time >= threshold
                        elif op == "<":
                            return row_time < threshold
                        elif op == "<=":
                            return row_time <= threshold

        # Simple equality: col == "value"
        match = re.match(r'(\w+)\s*==\s*"([^"]+)"', condition)
        if match:
            col, value = match.groups()
            return str(row.get(col)) == value

        # Simple inequality: col != "value"
        match = re.match(r'(\w+)\s*!=\s*"([^"]+)"', condition)
        if match:
            col, value = match.groups()
            return str(row.get(col)) != value

        # contains: col contains "substring"
        match = re.match(r'(\w+)\s+contains\s+"([^"]+)"', condition)
        if match:
            col, substring = match.groups()
            return substring.lower() in str(row.get(col, "")).lower()

        # startswith: col startswith "prefix"
        match = re.match(r'(\w+)\s+startswith\s+"([^"]+)"', condition)
        if match:
            col, prefix = match.groups()
            return str(row.get(col, "")).startswith(prefix)

        return True

    def _parse_timestamp(self, ts_str: Any) -> datetime | None:
        """Parse ISO timestamp string to datetime."""
        if not isinstance(ts_str, str):
            return None
        try:
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None
