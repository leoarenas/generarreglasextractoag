import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sql_rules import build_connection_string, connect_sql_server


def main() -> None:
    load_dotenv()
    connection = connect_sql_server(
        build_connection_string(
            os.environ["SQL_SERVER"],
            os.environ["SQL_DATABASE"],
            os.environ["SQL_USERNAME"],
            os.environ["SQL_PASSWORD"],
            os.environ.get("SQL_ODBC_DRIVER", "ODBC Driver 18 for SQL Server"),
            os.environ.get("SQL_ENCRYPT", "true").lower() == "true",
            os.environ.get("SQL_TRUST_SERVER_CERTIFICATE", "true").lower() == "true",
        )
    )
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT COUNT(*), SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END), "
            "COUNT(DISTINCT CONCAT(match_type, NCHAR(31), pattern)) "
            "FROM dbo.bank_pattern_rules WHERE bank_code = ?",
            "macro",
        )
        total, active, unique_keys = cursor.fetchone()
        print(f"total_macro: {total}")
        print(f"activas_macro: {active or 0}")
        print(f"claves_unicas_macro: {unique_keys}")
        cursor.execute(
            "SELECT priority, is_active, description_norm, confidence_score "
            "FROM dbo.bank_pattern_rules "
            "WHERE bank_code = ? AND match_type = ? AND pattern = ?",
            "macro",
            "contains",
            "N/D DBCR 25413 S/DB TASA GRAL",
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("No se encontro la regla consolidada esperada.")
        print(f"regla_consolidada_prioridad: {row[0]}")
        print(f"regla_consolidada_activa: {'si' if row[1] else 'no'}")
        print(f"regla_consolidada_descripcion: {row[2]}")
        print(f"regla_consolidada_confianza: {row[3]}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
