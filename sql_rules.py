import re
from dataclasses import dataclass
from typing import Any, Callable


RULE_COLUMNS = [
    "bank_code",
    "priority",
    "is_active",
    "match_type",
    "pattern",
    "description_norm",
    "tx_type",
    "entity_hint",
    "confidence_score",
    "notes",
]

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class SqlPublishResult:
    inserted: int
    updated: int
    deactivated: int

    @property
    def synchronized(self) -> int:
        return self.inserted + self.updated


def deduplicate_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Conserva una regla por clave, priorizando menor priority y mayor confianza."""
    selected: dict[tuple[str, str, str], dict[str, Any]] = {}
    for rule in rules:
        key = (
            str(rule["bank_code"]),
            str(rule["match_type"]),
            str(rule["pattern"]),
        )
        candidate_rank = (int(rule["priority"]), -float(rule["confidence_score"]))
        current = selected.get(key)
        if current is None:
            selected[key] = rule
            continue
        current_rank = (
            int(current["priority"]),
            -float(current["confidence_score"]),
        )
        if candidate_rank < current_rank:
            selected[key] = rule
    return list(selected.values())


def quote_table_name(table_name: str) -> str:
    parts = table_name.split(".")
    if len(parts) != 2 or any(not _IDENTIFIER.fullmatch(part) for part in parts):
        raise ValueError("SQL_RULES_TABLE debe tener el formato esquema.tabla.")
    return ".".join(f"[{part}]" for part in parts)


def build_connection_string(
    server: str,
    database: str,
    username: str,
    password: str,
    driver: str,
    encrypt: bool,
    trust_server_certificate: bool,
) -> str:
    def escape(value: str) -> str:
        return "{" + value.replace("}", "}}") + "}"

    return ";".join(
        [
            f"DRIVER={escape(driver)}",
            f"SERVER={escape(server)}",
            f"DATABASE={escape(database)}",
            f"UID={escape(username)}",
            f"PWD={escape(password)}",
            f"Encrypt={'yes' if encrypt else 'no'}",
            f"TrustServerCertificate={'yes' if trust_server_certificate else 'no'}",
        ]
    )


def connect_sql_server(connection_string: str) -> Any:
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError(
            "Instale pyodbc y Microsoft ODBC Driver 17 o 18 for SQL Server."
        ) from exc
    return pyodbc.connect(connection_string, autocommit=False)


def synchronize_active_rules(
    connection: Any,
    table_name: str,
    bank_code: str,
    rules: list[dict[str, Any]],
) -> SqlPublishResult:
    """Inserta/actualiza reglas y desactiva las ausentes, todo en una transaccion."""
    table = quote_table_name(table_name)
    keys = [(str(rule["match_type"]), str(rule["pattern"])) for rule in rules]
    if len(keys) != len(set(keys)):
        raise ValueError(
            "Hay reglas duplicadas para la clave bank_code + match_type + pattern."
        )
    if any(str(rule["bank_code"]) != bank_code for rule in rules):
        raise ValueError("Todas las reglas deben pertenecer al banco procesado.")

    cursor = connection.cursor()
    inserted = 0
    updated = 0
    deactivated = 0
    try:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        cursor.execute(
            f"SELECT [match_type], [pattern] FROM {table} WITH (UPDLOCK, HOLDLOCK) "
            "WHERE [bank_code] = ? AND [is_active] = 1",
            bank_code,
        )
        active_keys = {(str(row[0]), str(row[1])) for row in cursor.fetchall()}
        current_keys = set(keys)

        for match_type, pattern in sorted(active_keys - current_keys):
            cursor.execute(
                f"UPDATE {table} SET [is_active] = 0 "
                "WHERE [bank_code] = ? AND [match_type] = ? AND [pattern] = ? "
                "AND [is_active] = 1",
                bank_code,
                match_type,
                pattern,
            )
            deactivated += max(cursor.rowcount, 0)

        for rule in rules:
            cursor.execute(
                f"UPDATE {table} SET [priority] = ?, [is_active] = ?, "
                "[description_norm] = ?, [tx_type] = ?, [entity_hint] = ?, "
                "[confidence_score] = ?, [notes] = ? "
                "WHERE [bank_code] = ? AND [match_type] = ? AND [pattern] = ?",
                int(rule["priority"]),
                bool(rule["is_active"]),
                str(rule["description_norm"]),
                str(rule["tx_type"]),
                str(rule["entity_hint"]),
                float(rule["confidence_score"]),
                str(rule["notes"]),
                bank_code,
                str(rule["match_type"]),
                str(rule["pattern"]),
            )
            if cursor.rowcount:
                updated += cursor.rowcount
                continue
            placeholders = ", ".join("?" for _ in RULE_COLUMNS)
            columns = ", ".join(f"[{column}]" for column in RULE_COLUMNS)
            cursor.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                *[rule[column] for column in RULE_COLUMNS],
            )
            inserted += 1

        connection.commit()
        return SqlPublishResult(inserted, updated, deactivated)
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def publish_rules_to_sql(
    connection_string: str,
    table_name: str,
    bank_code: str,
    rules: list[dict[str, Any]],
    connect: Callable[[str], Any] = connect_sql_server,
) -> SqlPublishResult:
    connection = connect(connection_string)
    try:
        return synchronize_active_rules(connection, table_name, bank_code, rules)
    finally:
        connection.close()
