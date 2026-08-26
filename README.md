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

### Salida de reglas activas en SQL Server

Las reglas publicables se sincronizan en `dbo.bank_pattern_rules`. La identidad de
cada regla es `bank_code + match_type + pattern`: si existe se actualiza, si no
existe se inserta. Dentro de la misma transaccion, las reglas activas del banco que
ya no aparecen en la corrida se actualizan a `is_active = 0`.

Variables requeridas:

- `SQL_PUBLISH_ENABLED=true`
- `SQL_SERVER=vm-srv-sqldev`
- `SQL_DATABASE=Metalnor_Paralelo`
- `SQL_USERNAME`
- `SQL_PASSWORD`
- `SQL_RULES_TABLE=dbo.bank_pattern_rules`
- `SQL_ODBC_DRIVER=ODBC Driver 18 for SQL Server`

La tabla debe contener las diez columnas indicadas en la seccion Formato de salida.
Las credenciales deben permanecer en `.env` o en el gestor de secretos y nunca
versionarse. Si `RULES_SPREADSHEET_ID` sigue configurado, Google Sheets se mantiene
como salida adicional. Con `DRY_RUN=true` no se escribe en ninguno de los destinos.

## Instalacion local

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

## Primera configuracion por cliente, banco y cuenta

La primera ejecucion crea un perfil local sin modificar el motor de reglas:

```powershell
python main.py --setup --sample-file "C:\ruta\extracto_muestra.xlsx"
```

El asistente solicita obligatoriamente:

- nombre del banco
- numero, alias o ultimos cuatro caracteres de la cuenta
- tipo de cuenta; por ejemplo, Cuenta corriente, Caja de ahorro o Cuenta recaudadora
- moneda
- ruta del extracto de muestra o archivo adjunto disponible localmente, si no se
  paso por parametro

Se admiten archivos `CSV`, `XLSX`, `XLSM` y `PDF`. Los PDF deben contener texto y
tablas detectables; un documento compuesto solamente por imagen requiere OCR previo.
Si el PDF esta protegido, el asistente solicita la contraseña sin guardarla en el
perfil. En futuras corridas se proporciona mediante `PDF_PASSWORD`.

Luego detecta la hoja y la fila de encabezados, propone un diccionario de columnas,
permite corregirlo, muestra movimientos normalizados y solicita confirmacion. El
perfil queda versionado en `config/profiles/`.

Cada perfil utiliza por defecto su propio estado en `config/state/` y su propio
directorio de respaldos en `output/`. Esto evita mezclar el historial de clientes,
bancos o cuentas diferentes.

Para procesar futuros extractos con ese diccionario:

```powershell
$env:SOURCE_FILE="C:\ruta\extracto_nuevo.xlsx"
$env:PROFILE_FILE="config\profiles\banco_cuenta_moneda_v1.json"
python main.py
```

### Seleccion automatica desde una carpeta de Google Drive

Para que el agente busque el extracto automaticamente, configure el ID de la
carpeta y el perfil bancario:

```powershell
$env:DRIVE_FOLDER_ID="id_de_la_carpeta"
$env:DRIVE_FILE_PATTERN="*macro*.pdf"
$env:PROFILE_FILE="config\profiles\macro_1644_ars_v1.json"
$env:PDF_PASSWORD="contraseña_si_corresponde"
python main.py
```

El agente lista solamente los archivos que pertenecen directamente a esa carpeta,
descarta elementos enviados a la papelera y formatos no compatibles, aplica el
patron opcional y elige el archivo con el `modifiedTime` mas reciente de Google
Drive. Luego lo descarga en `.cache/drive/` y lo procesa con el perfil configurado.

Se admiten `CSV`, `XLSX`, `XLSM`, `PDF` y Google Sheets nativos, que se exportan
temporalmente como `XLSX`. `DRIVE_FOLDER_ID` tiene prioridad sobre `SOURCE_FILE`.
La cuenta de servicio debe tener al menos acceso de lectura a la carpeta.

### Ejecucion multibanco

La relacion entre bancos, carpetas y perfiles se define en
`config/drive_sources.json`. Cada banco puede tener su propia carpeta, patron de
archivos, variable de contraseña y uno o varios perfiles. El agente descarga una
sola vez el archivo mas reciente de cada carpeta, combina los movimientos de sus
perfiles y genera reglas por banco en una hoja independiente.

```powershell
$env:DRIVE_SOURCES_FILE="config/drive_sources.json"
$env:MACRO_PDF_PASSWORD="contraseña_si_corresponde"
python main.py
```

Los estados quedan en `config/state/<bank_code>.json`, los respaldos en
`output/<bank_code>/` y las reglas en `Reglas_<bank_code>`.

Las reglas que no alcanzan el umbral de confianza se guardan por separado en
`Reglas_<bank_code>_descartadas`, junto con el motivo, el umbral requerido, el
archivo fuente y la fecha de ejecución.

Si faltan columnas o aparecen columnas nuevas, el agente detiene la corrida para no
publicar reglas basadas en una interpretacion incorrecta. Para un formato nuevo se
debe ejecutar nuevamente `--setup`; se conserva la version anterior del perfil.

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
