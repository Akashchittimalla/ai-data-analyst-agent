"""Pure, dependency-free validation for user and model generated SQL."""

import re


FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|COPY|ATTACH|DETACH|INSTALL|LOAD|"
    r"EXPORT|IMPORT|CALL|PRAGMA|VACUUM|SET|USE|TRUNCATE|MERGE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


def validate_read_sql(sql: str) -> str:
    """Permit exactly one DuckDB SELECT/CTE statement and reject unsafe syntax."""
    clean_sql = sql.strip().rstrip(";").strip()
    if not clean_sql or ";" in clean_sql:
        raise ValueError("Only one read-only SQL statement is allowed.")
    if "--" in clean_sql or "/*" in clean_sql or FORBIDDEN_SQL.search(clean_sql):
        raise ValueError("Only read-only SELECT queries are allowed.")
    if not re.match(r"^(SELECT|WITH\b)", clean_sql, re.IGNORECASE):
        raise ValueError("Only SELECT queries are allowed.")
    return clean_sql
