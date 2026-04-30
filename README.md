# generarreglasextractoag

Base de proyecto para un agente que monitorea una Google Sheet de extracto bancario y mantiene actualizada una hoja de reglas de conciliacion.

## Que hace

El agente ejecuta este flujo:

1. Lee la hoja fuente configurada.
2. Normaliza el contenido relevante.
3. Calcula una huella del extracto.
4. Compara contra el ultimo estado procesado.
5. Si no hubo cambios, corta sin llamar al modelo.
6. Si hubo cambios, pide reglas nuevas o ajustadas al modelo.
7. Valida estrictamente el esquema de salida.
8. Guarda un backup JSON local.
9. Actualiza la hoja destino de reglas.
10. Persiste el nuevo estado.

## Estructura

- `main.py`: orquestador principal.
- `.env.example`: variables base de configuracion.
- `requirements.txt`: dependencias de Python.
- `skills/conciliacion-bancaria-macro/SKILL.md`: skill para invocar el agente.
- `.github/workflows/deploy.yml`: scheduler base con GitHub Actions.
- `output/`: backups JSON por corrida.
- `state.json`: estado persistido de la ultima ejecucion.

## Variables principales

- `GOOGLE_SERVICE_ACCOUNT_JSON` o `GOOGLE_SERVICE_ACCOUNT_FILE`
- `SOURCE_SPREADSHEET_ID`
- `SOURCE_SHEET_NAME`
- `RULES_SPREADSHEET_ID`
- `RULES_SHEET_NAME`
- `OPENAI_API_KEY`
- `LLM_MODEL`
- `BANK_CODE`
- `MIN_CONFIDENCE_AUTOPUBLISH`
- `MAX_SAMPLE_ROWS`
- `MAX_RULES`
- `RUN_ONCE`
- `DRY_RUN`

## Instalacion local

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

## Prueba segura

```powershell
$env:DRY_RUN="true"
$env:RUN_ONCE="true"
python main.py
```

## Corrida real

```powershell
$env:DRY_RUN="false"
$env:RUN_ONCE="true"
python main.py
```

## Scheduler

El workflow `.github/workflows/deploy.yml` queda listo para ejecucion manual o programada. Requiere cargar en GitHub Secrets:

- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `SOURCE_SPREADSHEET_ID`
- `RULES_SPREADSHEET_ID`
- `OPENAI_API_KEY`

Y opcionalmente en GitHub Variables:

- `SOURCE_SHEET_NAME`
- `RULES_SHEET_NAME`
- `LLM_MODEL`
- `BANK_CODE`
- `MIN_CONFIDENCE_AUTOPUBLISH`
- `MAX_SAMPLE_ROWS`
- `MAX_RULES`

## Formato de salida

Cada ejecucion imprime siempre:

```text
estado: <ok|sin_cambios|error>
hubo_cambios: <si|no>
reglas_generadas: <numero>
reglas_publicadas: <numero>
backup: <ruta o n/a>
observaciones: <texto breve>
```

## Notas operativas

- El agente no publica si la validacion falla.
- El agente no publica si encuentra reglas por debajo del umbral de confianza.
- En `DRY_RUN`, puede generar backup local pero no modifica la sheet destino ni actualiza `state.json`.
