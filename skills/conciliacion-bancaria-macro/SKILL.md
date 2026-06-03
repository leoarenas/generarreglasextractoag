---
name: conciliacion-bancaria-macro
description: Ejecuta el orquestador local main.py para monitorear un extracto bancario en Google Sheets, detectar cambios, generar reglas de conciliacion y actualizar una hoja de reglas validada.
---

# Skill: conciliacion-bancaria-macro

## Objetivo

Ejecutar directamente `main.py` para mantener actualizada la hoja de reglas de conciliacion bancaria a partir del extracto bancario fuente.

## Modo de uso

1. Verificar que exista `main.py`.
2. Verificar que exista `.env` o variables de entorno equivalentes.
3. Ejecutar `python main.py`.
4. Responder usando el resumen estructurado impreso por el script.

## Variables esperadas

- `GOOGLE_SERVICE_ACCOUNT_JSON` o `GOOGLE_SERVICE_ACCOUNT_FILE`
- `SOURCE_SPREADSHEET_ID`
- `SOURCE_SHEET_NAME`
- `RULES_SPREADSHEET_ID`
- `RULES_SHEET_NAME`
- `OPENAI_API_KEY`
- `LLM_MODEL`
- `BANK_CODE`
- `MAX_SAMPLE_ROWS`
- `MAX_RULES`
- `MIN_CONFIDENCE_AUTOPUBLISH`
- `DRY_RUN`
- `RUN_ONCE`

## Comando principal

```powershell
python main.py
```

## Reglas operativas

- No publicar si falla la validacion.
- No publicar si alguna regla queda por debajo del umbral de confianza.
- Si no hubo cambios, no llamar al modelo.
- Si `DRY_RUN=true`, permitir backup local pero no publicacion.
