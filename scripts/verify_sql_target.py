import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sql_rules import build_connection_string, connect_sql_server


EXPECTED_COLUMNS = {
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
}


def env_bool(name: str, default: str = "true") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    load_dotenv()
    table = os.environ.get("SQL_RULES_TABLE", "dbo.bank_pattern_rules")
    connection_string = build_connection_string(
        os.environ.get("SQL_SERVER", "vm-srv-sqldev"),
        os.environ.get("SQL_DATABASE", "Metalnor_Paralelo"),
        os.environ["SQL_USERNAME"],
        os.environ["SQL_PASSWORD"],
        os.environ.get("SQL_ODBC_DRIVER", "ODBC Driver 18 for SQL Server"),
        env_bool("SQL_ENCRYPT"),
        env_bool("SQL_TRUST_SERVER_CERTIFICATE"),
    )
    connection = connect_sql_server(connection_string)
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT c.name, t.name, c.max_length, c.is_nullable "
            "FROM sys.columns AS c "
            "JOIN sys.types AS t ON c.user_type_id = t.user_type_id "
            "WHERE c.object_id = OBJECT_ID(?) ORDER BY c.column_id",
            table,
        )
        rows = cursor.fetchall()
        if not rows:
            raise RuntimeError(f"No existe la tabla {table} o el usuario no puede verla.")
        found = {str(row[0]).lower() for row in rows}
        missing = sorted(EXPECTED_COLUMNS - found)
        print("conexion: ok")
        print(f"tabla: {table}")
        print(f"columnas_detectadas: {len(rows)}")
        for row in rows:
            print(
                f"columna: {row[0]} | tipo: {row[1]} | "
                f"longitud: {row[2]} | nullable: {'si' if row[3] else 'no'}"
            )
        if missing:
            raise RuntimeError("Faltan columnas requeridas: " + ", ".join(missing))
        cursor.execute(
            f"SELECT COUNT(*), SUM(CASE WHEN [is_active] = 1 THEN 1 ELSE 0 END) "
            f"FROM {table} WHERE [bank_code] = ?",
            os.environ.get("BANK_CODE", "macro"),
        )
        total, active = cursor.fetchone()
        print("esquema: compatible")
        print(f"registros_banco: {total}")
        print(f"registros_activos_banco: {active or 0}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
