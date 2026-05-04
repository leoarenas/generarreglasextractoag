import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from json_repair import repair_json
from openai import OpenAI


ALLOWED_MATCH_TYPES = {
    "contains",
    "equals",
    "regex",
    "starts_with",
    "ends_with",
    "semantic",
}

EXPECTED_COLUMNS = [
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

ALLOWED_TX_TYPES = {"credito", "debito", "mixto"}


@dataclass
class Settings:
    google_service_account_json: str | None
    google_service_account_file: str | None
    source_spreadsheet_id: str
    source_sheet_name: str
    rules_spreadsheet_id: str
    rules_sheet_name: str
    poll_interval_seconds: int
    bank_code: str
    output_dir: Path
    state_file: Path
    min_confidence_autopublish: float
    llm_provider: str
    llm_model: str
    max_sample_rows: int
    max_rules: int
    run_once: bool
    dry_run: bool


@dataclass
class RunSummary:
    estado: str
    hubo_cambios: str
    reglas_generadas: int
    reglas_publicadas: int
    backup: str
    observaciones: str


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        google_service_account_json=os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"),
        google_service_account_file=os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE"),
        source_spreadsheet_id=os.environ["SOURCE_SPREADSHEET_ID"],
        source_sheet_name=os.environ.get("SOURCE_SHEET_NAME", "Hoja 1"),
        rules_spreadsheet_id=os.environ["RULES_SPREADSHEET_ID"],
        rules_sheet_name=os.environ.get("RULES_SHEET_NAME", "Reglas"),
        poll_interval_seconds=int(os.environ.get("POLL_INTERVAL_SECONDS", "900")),
        bank_code=os.environ.get("BANK_CODE", "macro"),
        output_dir=Path(os.environ.get("OUTPUT_DIR", "output")),
        state_file=Path(os.environ.get("STATE_FILE", "state.json")),
        min_confidence_autopublish=float(
            os.environ.get("MIN_CONFIDENCE_AUTOPUBLISH", "0.85")
        ),
        llm_provider=os.environ.get("LLM_PROVIDER", "openai"),
        llm_model=os.environ.get("LLM_MODEL", "gpt-5.4-mini"),
        max_sample_rows=int(os.environ.get("MAX_SAMPLE_ROWS", "120")),
        max_rules=int(os.environ.get("MAX_RULES", "30")),
        run_once=parse_bool(os.environ.get("RUN_ONCE", "true")),
        dry_run=parse_bool(os.environ.get("DRY_RUN", "false")),
    )


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.write_text(json.dumps(state, indent=2, ensure_ascii=True), encoding="utf-8")


def hash_rows(rows: list[list[str]]) -> str:
    payload = json.dumps(rows, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_gspread_client(settings: Settings) -> gspread.Client:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    if settings.google_service_account_json:
        credentials_info = json.loads(settings.google_service_account_json)
        credentials = Credentials.from_service_account_info(
            credentials_info,
            scopes=scopes,
        )
        return gspread.authorize(credentials)

    if settings.google_service_account_file:
        credentials = Credentials.from_service_account_file(
            settings.google_service_account_file,
            scopes=scopes,
        )
        return gspread.authorize(credentials)

    raise ValueError(
        "Falta configurar GOOGLE_SERVICE_ACCOUNT_JSON o GOOGLE_SERVICE_ACCOUNT_FILE."
    )


def normalize_cell(value: Any) -> str:
    return str(value).strip()


def fetch_source_rows(settings: Settings) -> list[list[str]]:
    client = get_gspread_client(settings)
    spreadsheet = client.open_by_key(settings.source_spreadsheet_id)
    worksheet = spreadsheet.worksheet(settings.source_sheet_name)
    all_rows = worksheet.get_all_values()

    if not all_rows:
        raise ValueError("La hoja fuente esta vacia.")

    normalized_rows = [
        [normalize_cell(cell) for cell in row]
        for row in all_rows
        if any(normalize_cell(cell) for cell in row)
    ]
    header = normalized_rows[0]
    selected_indexes = [index for index, name in enumerate(header) if name]
    if not selected_indexes:
        raise ValueError("No se detectaron encabezados validos en la hoja fuente.")

    rows = []
    for row in normalized_rows:
        filtered_row = [row[index] if index < len(row) else "" for index in selected_indexes]
        rows.append(filtered_row)

    if len(rows) < 2:
        raise ValueError("La hoja fuente no tiene filas de datos.")

    return rows


def detect_changed_rows(
    previous_rows: list[list[str]] | None, current_rows: list[list[str]]
) -> tuple[int, int]:
    if not previous_rows:
        return len(current_rows) - 1, 0

    previous_map = {row_key(row): row for row in previous_rows[1:]}
    current_map = {row_key(row): row for row in current_rows[1:]}

    new_rows = sum(1 for key in current_map if key not in previous_map)
    modified_rows = sum(
        1
        for key, row in current_map.items()
        if key in previous_map and row != previous_map[key]
    )
    return new_rows, modified_rows


def row_key(row: list[str]) -> str:
    return hashlib.sha1(
        json.dumps(row, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_prompt_payload(
    rows: list[list[str]], bank_code: str, max_sample_rows: int, max_rules: int
) -> dict[str, Any]:
    header = rows[0]
    data_rows = rows[1:]
    sample_rows = data_rows[:max_sample_rows]

    return {
        "bank_code": bank_code,
        "columns": header,
        "rules_schema": EXPECTED_COLUMNS,
        "allowed_match_type": sorted(ALLOWED_MATCH_TYPES),
        "allowed_tx_type": sorted(ALLOWED_TX_TYPES),
        "max_rules": max_rules,
        "instructions": [
            "Redactar el contenido en espanol.",
            "Priorizar patrones estables y reutilizables.",
            "No inventar atributos ni entidades no visibles en el extracto.",
            "Usar confidence_score entre 0 y 1.",
            "Usar solo informacion visible en las filas de muestra.",
            "Si la confianza es baja, ser conservador.",
            "Devolver exclusivamente JSON valido UTF-8 sin markdown.",
            "La salida debe ser un objeto con la clave rules.",
        ],
        "sample_rows": [dict(zip(header, row)) for row in sample_rows],
    }


def build_rules_prompt(payload: dict[str, Any]) -> str:
    return (
        "Sos un analista experto en conciliacion bancaria.\n"
        "Tu tarea es generar reglas reutilizables a partir de un extracto bancario.\n"
        "Responde solo con JSON valido.\n\n"
        "Formato de salida obligatorio:\n"
        "{\n"
        '  "rules": [\n'
        "    {\n"
        '      "bank_code": "string",\n'
        '      "priority": 1,\n'
        '      "is_active": true,\n'
        '      "match_type": "contains|equals|regex|starts_with|ends_with|semantic",\n'
        '      "pattern": "string",\n'
        '      "description_norm": "string",\n'
        '      "tx_type": "credito|debito|mixto",\n'
        '      "entity_hint": "string",\n'
        '      "confidence_score": 0.0,\n'
        '      "notes": "string"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Contexto de entrada:\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def generate_rules_with_llm(payload: dict[str, Any], settings: Settings) -> list[dict[str, Any]]:
    if settings.llm_provider != "openai":
        raise ValueError(f"LLM_PROVIDER no soportado: {settings.llm_provider}")

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    prompt = build_rules_prompt(payload)
    response = client.responses.create(
        model=settings.llm_model,
        input=prompt,
    )
    raw_text = response.output_text
    if not raw_text.strip():
        raise ValueError("La respuesta del modelo vino vacia.")

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = json.loads(repair_json(raw_text))

    rules = parsed.get("rules")
    if not isinstance(rules, list):
        raise ValueError("La respuesta del modelo no contiene una lista en 'rules'.")
    return rules


def validate_rule(rule: dict[str, Any], settings: Settings) -> None:
    missing = [column for column in EXPECTED_COLUMNS if column not in rule]
    extra = [column for column in rule if column not in EXPECTED_COLUMNS]
    if missing or extra:
        raise ValueError(f"Esquema invalido. Faltan={missing} Sobran={extra}")

    if rule["match_type"] not in ALLOWED_MATCH_TYPES:
        raise ValueError(f"match_type invalido: {rule['match_type']}")

    if rule["tx_type"] not in ALLOWED_TX_TYPES:
        raise ValueError(f"tx_type invalido: {rule['tx_type']}")

    if not isinstance(rule["priority"], int):
        raise ValueError(f"priority invalido: {rule['priority']}")

    if not isinstance(rule["is_active"], bool):
        raise ValueError(f"is_active invalido: {rule['is_active']}")

    if not isinstance(rule["pattern"], str) or not rule["pattern"].strip():
        raise ValueError("pattern vacio")

    if not isinstance(rule["description_norm"], str) or not rule["description_norm"].strip():
        raise ValueError("description_norm vacio")

    score = float(rule["confidence_score"])
    if not 0 <= score <= 1:
        raise ValueError(f"confidence_score fuera de rango: {score}")


def validate_rules(rules: list[dict[str, Any]], settings: Settings) -> None:
    if not rules:
        raise ValueError("No se generaron reglas.")
    if len(rules) > settings.max_rules:
        raise ValueError(
            f"Se generaron demasiadas reglas: {len(rules)}. Maximo permitido: {settings.max_rules}."
        )

    for rule in rules:
        validate_rule(rule, settings)


def split_rules_by_confidence(
    rules: list[dict[str, Any]], min_confidence: float
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    publishable_rules: list[dict[str, Any]] = []
    discarded_rules: list[dict[str, Any]] = []

    for rule in rules:
        if float(rule["confidence_score"]) < min_confidence:
            discarded_rules.append(rule)
        else:
            publishable_rules.append(rule)

    return publishable_rules, discarded_rules


def save_backup(rules: list[dict[str, Any]], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = output_dir / f"rules_{timestamp}.json"
    target.write_text(json.dumps(rules, indent=2, ensure_ascii=True), encoding="utf-8")
    return target


def to_sheet_values(rules: list[dict[str, Any]]) -> list[list[Any]]:
    values: list[list[Any]] = [EXPECTED_COLUMNS]
    for rule in rules:
        values.append([rule[column] for column in EXPECTED_COLUMNS])
    return values


def get_or_create_worksheet(
    spreadsheet: gspread.Spreadsheet, title: str, rows: int, cols: int
) -> gspread.Worksheet:
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)


def publish_rules(settings: Settings, rules: list[dict[str, Any]]) -> int:
    if settings.dry_run:
        logging.info("DRY_RUN activo. No se publican cambios en Google Sheets.")
        return 0

    client = get_gspread_client(settings)
    spreadsheet = client.open_by_key(settings.rules_spreadsheet_id)
    worksheet = get_or_create_worksheet(
        spreadsheet,
        settings.rules_sheet_name,
        rows=max(len(rules) + 10, 50),
        cols=len(EXPECTED_COLUMNS),
    )
    values = to_sheet_values(rules)
    worksheet.clear()
    worksheet.update(values=values, range_name="A1")
    return len(rules)


def print_summary(summary: RunSummary) -> None:
    print(f"estado: {summary.estado}")
    print(f"hubo_cambios: {summary.hubo_cambios}")
    print(f"reglas_generadas: {summary.reglas_generadas}")
    print(f"reglas_publicadas: {summary.reglas_publicadas}")
    print(f"backup: {summary.backup}")
    print(f"observaciones: {summary.observaciones}")


def run_once(settings: Settings) -> RunSummary:
    state = load_state(settings.state_file)
    rows = fetch_source_rows(settings)
    current_hash = hash_rows(rows)

    if state.get("source_hash") == current_hash:
        return RunSummary(
            estado="sin_cambios",
            hubo_cambios="no",
            reglas_generadas=0,
            reglas_publicadas=0,
            backup="n/a",
            observaciones="La hoja fuente no tuvo cambios relevantes.",
        )

    previous_rows = state.get("rows")
    new_rows, modified_rows = detect_changed_rows(previous_rows, rows)

    payload = build_prompt_payload(
        rows,
        settings.bank_code,
        settings.max_sample_rows,
        settings.max_rules,
    )
    rules = generate_rules_with_llm(payload, settings)
    validate_rules(rules, settings)

    backup_path = save_backup(rules, settings.output_dir)
    publishable_rules, discarded_rules = split_rules_by_confidence(
        rules, settings.min_confidence_autopublish
    )

    if not publishable_rules:
        discarded_preview = ", ".join(
            f"{rule['pattern']} ({rule['confidence_score']})"
            for rule in discarded_rules[:5]
        )
        return RunSummary(
            estado="error",
            hubo_cambios="si",
            reglas_generadas=len(rules),
            reglas_publicadas=0,
            backup=str(backup_path),
            observaciones=(
                "Todas las reglas quedaron por debajo del umbral de confianza. "
                f"Descartadas: {len(discarded_rules)}. Ejemplos: {discarded_preview}"
            ),
        )

    published_count = publish_rules(settings, publishable_rules)

    if not settings.dry_run:
        save_state(
            settings.state_file,
            {
                "source_hash": current_hash,
                "last_run_utc": datetime.now(timezone.utc).isoformat(),
                "last_backup": str(backup_path),
                "rules_count": len(publishable_rules),
                "discarded_rules_count": len(discarded_rules),
                "rows": rows,
            },
        )

    observation = (
        f"Cambios detectados. Filas nuevas: {new_rows}. Filas modificadas: {modified_rows}."
    )
    if discarded_rules:
        discarded_preview = ", ".join(
            f"{rule['pattern']} ({rule['confidence_score']})"
            for rule in discarded_rules[:5]
        )
        observation += (
            f" Se descartaron {len(discarded_rules)} reglas por baja confianza. "
            f"Ejemplos: {discarded_preview}."
        )
    if settings.dry_run:
        observation += " DRY_RUN activo; no se publico en la sheet destino."

    return RunSummary(
        estado="ok",
        hubo_cambios="si",
        reglas_generadas=len(rules),
        reglas_publicadas=published_count,
        backup=str(backup_path),
        observaciones=observation,
    )


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    settings = load_settings()

    while True:
        try:
            summary = run_once(settings)
        except Exception as exc:
            logging.exception("Fallo la corrida: %s", exc)
            summary = RunSummary(
                estado="error",
                hubo_cambios="no",
                reglas_generadas=0,
                reglas_publicadas=0,
                backup="n/a",
                observaciones=str(exc),
            )

        print_summary(summary)

        if settings.run_once:
            break
        time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    main()
