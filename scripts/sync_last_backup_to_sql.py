import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import load_settings, split_rules_by_confidence, validate_rules
from sql_rules import deduplicate_rules, publish_rules_to_sql


def main() -> None:
    load_dotenv()
    settings = load_settings()
    state_path = Path("config/state") / f"{settings.bank_code}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    backup_path = Path(state["last_backup"])
    rules = json.loads(backup_path.read_text(encoding="utf-8"))
    validate_rules(rules, settings)
    publishable, discarded = split_rules_by_confidence(
        rules, settings.min_confidence_autopublish
    )
    publishable_before_deduplication = len(publishable)
    publishable = deduplicate_rules(publishable)
    if not settings.sql_connection_string:
        raise RuntimeError("Falta la conexion SQL Server.")
    result = publish_rules_to_sql(
        settings.sql_connection_string,
        settings.sql_rules_table,
        settings.bank_code,
        publishable,
    )
    print(f"backup: {backup_path}")
    print(f"reglas_evaluadas: {len(rules)}")
    print(f"reglas_descartadas: {len(discarded)}")
    print(
        "reglas_duplicadas_consolidadas: "
        f"{publishable_before_deduplication - len(publishable)}"
    )
    print(f"insertadas: {result.inserted}")
    print(f"actualizadas: {result.updated}")
    print(f"inactivadas: {result.deactivated}")


if __name__ == "__main__":
    main()
