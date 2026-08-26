# Manual Tecnico de Implementacion

## Agente de Conciliacion Bancaria con Google Sheets y OpenAI

## 1. Objetivo del documento

Este documento describe paso a paso como implementar un agente de conciliacion bancaria que:

- lee un extracto bancario desde Google Sheets
- detecta cambios relevantes respecto de la ultima ejecucion
- genera o ajusta reglas de conciliacion con OpenAI
- valida la salida antes de publicar
- actualiza una hoja destino de reglas
- guarda respaldo local de cada corrida
- puede ejecutarse en forma manual, local o programada con GitHub Actions

### Configuracion local reutilizable por cliente

Para instalaciones con formatos bancarios diferentes, ejecutar `python main.py --setup`
en la primera puesta en marcha. El asistente solicita obligatoriamente nombre del banco,
numero, alias o ultimos cuatro caracteres de la cuenta; tipo de cuenta (por ejemplo,
Cuenta corriente, Caja de ahorro o Cuenta recaudadora); moneda; y la ruta de un extracto
de muestra o archivo adjunto disponible localmente. Admite CSV, XLSX, XLSM y PDF con
texto y tablas detectables. Detecta la
estructura del archivo, propone el diccionario de columnas, permite corregirlo, presenta
una vista previa normalizada y guarda un perfil local versionado.

El motor principal recibe siempre el esquema normalizado y no depende de los nombres de
columnas del banco. Las corridas posteriores usan `SOURCE_FILE` y `PROFILE_FILE`. Un
cambio de columnas detiene la ejecucion y requiere crear una nueva version del perfil.
El estado y los respaldos quedan aislados por perfil.

### Lectura automatica desde una carpeta de Google Drive

Cuando se configura `DRIVE_FOLDER_ID`, el agente consulta los archivos ubicados
directamente en esa carpeta, excluye los enviados a la papelera y los formatos no
compatibles, aplica `DRIVE_FILE_PATTERN` si fue definido y selecciona el archivo con
el `modifiedTime` mas reciente. El archivo se descarga temporalmente y se procesa con
`PROFILE_FILE`. Este origen tiene prioridad sobre `SOURCE_FILE`.

La cuenta de servicio configurada debe tener acceso de lectura a la carpeta. Se
admiten CSV, XLSX, XLSM, PDF y Google Sheets nativos exportados temporalmente a XLSX.

Las reglas que quedan por debajo del umbral de confianza se registran en
`Reglas_<bank_code>_descartadas` con el motivo, el umbral requerido, el archivo
fuente y la fecha de ejecución. No se mezclan con las reglas activas.

El objetivo es reutilizar este procedimiento como base de implementacion para clientes nuevos.

## 2. Alcance funcional

El agente implementado resuelve este flujo:

1. Leer una Google Sheet fuente con movimientos bancarios.
2. Tomar una pestaña especifica, por ejemplo `Hoja 1`.
3. Normalizar filas y columnas relevantes.
4. Calcular una huella del contenido.
5. Comparar con el ultimo estado procesado.
6. Si no hay cambios, no llamar al modelo y finalizar.
7. Si hay cambios, enviar una muestra estructurada al modelo.
8. Obtener reglas en formato JSON.
9. Validar esquema, tipos, campos permitidos y confianza.
10. Descartar reglas por debajo del umbral de confianza.
11. Publicar las reglas validas en la hoja destino.
12. Guardar backup local y actualizar `state.json`.

## 3. Arquitectura general

## 3.1 Componentes

- `Google Sheets`
  Fuente de extracto bancario y destino de reglas.

- `OpenAI API`
  Motor LLM para inferencia de reglas reutilizables.

- `Python`
  Orquestador principal del agente.

- `GitHub`
  Repositorio, versionado y automatizacion programada.

- `GitHub Actions`
  Scheduler para ejecucion periodica.

## 3.2 Componentes del repositorio

Archivos principales:

- `main.py`
  Orquestador del agente.

- `.env.example`
  Plantilla de configuracion local.

- `requirements.txt`
  Dependencias Python.

- `skills/conciliacion-bancaria-macro/SKILL.md`
  Skill local para invocar el agente desde Codex.

- `.github/workflows/deploy.yml`
  Workflow de GitHub Actions.

- `README.md`
  Instrucciones operativas resumidas.

- `state.json`
  Estado persistido de la ultima corrida.

- `output/`
  Backups JSON generados por corrida.

## 4. Herramientas utilizadas

## 4.1 Herramientas base

- `Python 3.11`
- `pip`
- `git`
- `GitHub`
- `Google Cloud`
- `Google Sheets`
- `OpenAI API`

## 4.2 Librerias Python

Dependencias actuales:

- `gspread`
- `google-auth`
- `python-dotenv`
- `openai`
- `json-repair`

## 4.3 Responsabilidad de cada libreria

- `gspread`
  Lectura y escritura de Google Sheets.

- `google-auth`
  Autenticacion con service account.

- `python-dotenv`
  Carga de variables desde `.env`.

- `openai`
  Llamadas a la API de OpenAI.

- `json-repair`
  Reparacion de JSON si la salida del modelo llega levemente malformada.

## 5. Requisitos previos por cliente

Antes de implementar el agente para un cliente, se necesita:

- acceso a una cuenta GitHub para alojar el repositorio
- acceso a una cuenta de OpenAI con API habilitada
- acceso a un proyecto de Google Cloud
- permiso para crear o administrar una `service account`
- acceso a la Google Sheet fuente
- acceso a la Google Sheet destino
- definicion del nombre de pestaña fuente y destino
- acuerdo sobre frecuencia de ejecucion
- acuerdo sobre umbral minimo de confianza para publicar

## 6. Estructura recomendada de datos

## 6.1 Hoja fuente

La hoja fuente debe contener movimientos bancarios con encabezados claros. El agente actual fue pensado para estructuras como:

- `Fecha`
- `Nro. de Referencia`
- `Causal`
- `Concepto`
- `Importe`
- `Saldo`

Puede haber columnas vacias intermedias. El agente filtra columnas vacias del encabezado.

## 6.2 Hoja destino

La hoja destino de reglas debe usar exactamente estas columnas:

- `bank_code`
- `priority`
- `is_active`
- `match_type`
- `pattern`
- `description_norm`
- `tx_type`
- `entity_hint`
- `confidence_score`
- `notes`

## 7. Salida esperada del modelo

Cada regla debe cumplir:

- `bank_code`: texto
- `priority`: entero
- `is_active`: boolean
- `match_type`: uno de `contains`, `equals`, `regex`, `starts_with`, `ends_with`, `semantic`
- `pattern`: texto no vacio
- `description_norm`: texto no vacio
- `tx_type`: uno de `credito`, `debito`, `mixto`
- `entity_hint`: texto, puede ser vacio
- `confidence_score`: numero entre `0` y `1`
- `notes`: texto

## 8. Configuracion de Google Cloud

## 8.1 Crear proyecto

1. Ingresar a Google Cloud Console.
2. Crear un proyecto nuevo o usar uno existente del cliente.
3. Nombrarlo con algun criterio como:
   `agente-conciliacion-<cliente>`

## 8.2 Habilitar APIs

En el proyecto, habilitar:

- `Google Sheets API`
- `Google Drive API`

## 8.3 Crear Service Account

1. Ir a `IAM y administracion` > `Service Accounts`.
2. Crear una nueva cuenta de servicio.
3. Asignar un nombre identificable.
4. Generar una clave JSON.
5. Descargar el archivo y resguardarlo de forma segura.

## 8.4 Permisos de la Service Account

En general, no hace falta asignar un rol amplio a nivel proyecto para leer y escribir Sheets compartidas. Lo importante es:

- que exista la service account
- que la clave JSON sea valida
- que las Sheets esten compartidas con el `client_email` de esa cuenta

## 8.5 Compartir las Google Sheets

Compartir con el `client_email` de la service account:

- Sheet fuente: minimo `Lector`
- Sheet destino: minimo `Editor`

En la practica inicial, se recomienda `Editor` en ambas para simplificar pruebas.

## 9. Configuracion de OpenAI

## 9.1 Requisito

Se necesita una API key valida del cliente o del proveedor del servicio.

## 9.2 Variable requerida

- `OPENAI_API_KEY`

## 9.3 Modelo recomendado

Variable:

- `LLM_MODEL`

Valor inicial sugerido:

- `gpt-5.4-mini`

Motivo:

- buena relacion costo/resultado
- suficiente para clasificacion y generacion de reglas

## 10. Configuracion del proyecto local

## 10.1 Clonar o copiar base

Trabajar sobre un repositorio por cliente o una plantilla parametrizable.

## 10.2 Crear entorno virtual

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 10.3 Crear `.env`

Partir de `.env.example`.

```powershell
Copy-Item .env.example .env
```

## 10.4 Variables de entorno requeridas

### Google

- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `GOOGLE_SERVICE_ACCOUNT_FILE`

Usar solo una de las dos.

### Sheets

- `SOURCE_SPREADSHEET_ID`
- `SOURCE_SHEET_NAME`
- `RULES_SPREADSHEET_ID`
- `RULES_SHEET_NAME`

### Ejecucion

- `POLL_INTERVAL_SECONDS`
- `RUN_ONCE`
- `DRY_RUN`
- `LOG_LEVEL`
- `STATE_FILE`
- `OUTPUT_DIR`

### OpenAI

- `LLM_PROVIDER`
- `LLM_MODEL`
- `OPENAI_API_KEY`

### Negocio

- `BANK_CODE`
- `MIN_CONFIDENCE_AUTOPUBLISH`
- `MAX_SAMPLE_ROWS`
- `MAX_RULES`

## 10.5 Ejemplo de `.env`

```env
GOOGLE_SERVICE_ACCOUNT_JSON=
GOOGLE_SERVICE_ACCOUNT_FILE=C:\ruta\service-account.json

SOURCE_SPREADSHEET_ID=google_sheet_fuente_id
SOURCE_SHEET_NAME=Hoja 1

RULES_SPREADSHEET_ID=google_sheet_destino_id
RULES_SHEET_NAME=Reglas

POLL_INTERVAL_SECONDS=900
RUN_ONCE=true
DRY_RUN=false
LOG_LEVEL=INFO

LLM_PROVIDER=openai
LLM_MODEL=gpt-5.4-mini
OPENAI_API_KEY=sk-xxxx

BANK_CODE=macro
OUTPUT_DIR=output
STATE_FILE=state.json
MIN_CONFIDENCE_AUTOPUBLISH=0.85
MAX_SAMPLE_ROWS=120
MAX_RULES=30
```

## 11. Seguridad y resguardo

## 11.1 Nunca subir al repositorio

- `.env`
- `service_account.json`
- `state.json`
- `output/`

## 11.2 Archivos que deben estar en `.gitignore`

- `.env`
- `service_account.json`
- `state.json`
- `output/`
- `logs/`
- `.venv/`
- `__pycache__/`

## 11.3 Recomendacion operativa

- usar una service account distinta por cliente si es posible
- usar una API key de OpenAI separada por cliente o por entorno
- evitar usar credenciales personales del implementador

## 12. Funcionamiento del agente

## 12.1 Deteccion de cambios

El agente:

1. lee todas las filas no vacias
2. elimina columnas sin encabezado
3. normaliza valores
4. genera `source_hash`
5. compara contra el `source_hash` guardado en `state.json`

Si no hay diferencia:

- no llama al modelo
- no escribe en la hoja destino
- responde `sin_cambios`

## 12.2 Generacion de reglas

Si hay cambios:

- toma hasta `MAX_SAMPLE_ROWS`
- arma payload estructurado
- llama al modelo OpenAI
- repara JSON si hace falta
- valida las reglas

## 12.3 Filtro por confianza

Comportamiento actual:

- si una regla queda debajo de `MIN_CONFIDENCE_AUTOPUBLISH`, se descarta
- las reglas restantes se publican
- si todas quedan debajo del umbral, no se publica nada

## 12.4 Publicacion

El agente:

- busca o crea la pestaña destino
- limpia su contenido
- escribe encabezados y reglas validas

## 12.5 Persistencia

Si `DRY_RUN=false`, guarda:

- `source_hash`
- fecha de ultima corrida
- ruta del ultimo backup
- cantidad de reglas publicadas
- cantidad de reglas descartadas
- filas procesadas

## 13. Ejecucion local

## 13.1 Prueba segura sin publicar

```powershell
$env:DRY_RUN="true"
$env:RUN_ONCE="true"
python main.py
```

## 13.2 Corrida real unica

```powershell
$env:DRY_RUN="false"
$env:RUN_ONCE="true"
python main.py
```

## 13.3 Modo continuo local

```powershell
$env:RUN_ONCE="false"
python main.py
```

## 14. Reproceso manual

## 14.1 Por que no reprocesa

Porque compara contra `state.json`.

## 14.2 Como forzar reproceso local

Opcion 1:

```powershell
Remove-Item .\state.json
python main.py
```

Opcion 2:

```powershell
$env:STATE_FILE="state_reproceso.json"
python main.py
```

## 14.3 Reproceso seguro sin publicar

```powershell
$env:DRY_RUN="true"
Remove-Item .\state.json
python main.py
```

## 15. Implementacion con GitHub Actions

## 15.1 Objetivo

Permitir ejecucion programada sin depender de una PC local encendida.

## 15.2 Workflow actual

El workflow:

1. hace checkout del repo
2. instala Python
3. restaura cache de `state.json` y `output`
4. instala dependencias
5. construye un `.env` temporal desde secrets y variables
6. ejecuta `python main.py`
7. guarda cache de estado
8. sube artifacts

## 15.3 Secrets requeridos en GitHub

En `Settings` > `Secrets and variables` > `Actions` > `Secrets`

Crear:

- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `SOURCE_SPREADSHEET_ID`
- `RULES_SPREADSHEET_ID`
- `OPENAI_API_KEY`

## 15.4 Variables recomendadas en GitHub

En `Settings` > `Secrets and variables` > `Actions` > `Variables`

Crear:

- `SOURCE_SHEET_NAME`
- `RULES_SHEET_NAME`
- `LLM_MODEL`
- `BANK_CODE`
- `MIN_CONFIDENCE_AUTOPUBLISH`
- `MAX_SAMPLE_ROWS`
- `MAX_RULES`

## 15.5 Valores iniciales sugeridos

- `SOURCE_SHEET_NAME=Hoja 1`
- `RULES_SHEET_NAME=Reglas`
- `LLM_MODEL=gpt-5.4-mini`
- `BANK_CODE=macro`
- `MIN_CONFIDENCE_AUTOPUBLISH=0.85`
- `MAX_SAMPLE_ROWS=120`
- `MAX_RULES=30`

## 15.6 Scheduler

La frecuencia actual se controla por cron en GitHub Actions.

Ejemplo:

- cada 1 hora
- cada 30 minutos
- cada 15 minutos

La frecuencia debe elegirse segun:

- volumen de movimientos
- costo permitido
- urgencia de actualizacion

## 15.7 Reproceso en GitHub Actions

Como el workflow cachea `state.json`, puede no reprocesar si la huella no cambia.

Para forzarlo:

### Opcion 1

Borrar la cache desde GitHub:

- `Actions` > `Caches`

### Opcion 2

Cambiar temporalmente el nombre del archivo de estado:

- `STATE_FILE=state_reproceso.json`

### Opcion 3

Ejecutar una variante del workflow que ignore estado previo.

## 16. Permisos y accesos por rol

## 16.1 Cliente

Debe proveer o aprobar:

- acceso a las Google Sheets
- acceso o alta de Google Cloud
- API key o aprobacion de uso de OpenAI
- aprobacion de frecuencia de ejecucion
- aprobacion de reglas de negocio

## 16.2 Implementador tecnico

Debe tener:

- acceso al repositorio GitHub
- permiso para configurar Actions
- permiso para cargar secrets y variables
- acceso de prueba a las Sheets

## 16.3 Service Account

Debe tener:

- acceso a la Sheet fuente
- acceso a la Sheet destino

No necesita acceso humano interactivo.

## 17. Procedimiento de implementacion en cliente nuevo

## 17.1 Preparacion

1. Crear repo o clonar plantilla.
2. Configurar Google Cloud del cliente.
3. Crear service account.
4. Habilitar Sheets API y Drive API.
5. Compartir Sheets con la service account.
6. Obtener API key de OpenAI.

## 17.2 Parametrizacion

1. Completar `.env` local.
2. Probar `DRY_RUN=true`.
3. Revisar salida del modelo.
4. Ajustar `MIN_CONFIDENCE_AUTOPUBLISH`.
5. Ejecutar corrida real.

## 17.3 Productivizacion

1. Push de repo.
2. Configurar GitHub Secrets.
3. Configurar GitHub Variables.
4. Ejecutar workflow manual.
5. Validar hoja destino.
6. Activar scheduler.

## 18. Validaciones recomendadas antes de salir a produccion

- la service account puede abrir ambas Sheets
- la hoja fuente tiene encabezados consistentes
- la hoja destino tiene permisos de escritura
- OpenAI responde correctamente
- `DRY_RUN=true` funciona
- la corrida real publica correctamente
- `state.json` se guarda y se reutiliza
- el workflow de GitHub Actions termina en verde

## 19. Troubleshooting

## 19.1 Error `missing fields token_uri, client_email`

Causa:

- se uso un `client_secret.json` OAuth y no una service account

Solucion:

- reemplazar por JSON de service account

## 19.2 Error `invalid_grant: account not found`

Causa probable:

- service account inexistente, borrada o clave invalida

Solucion:

- regenerar clave JSON
- verificar existencia de la cuenta en Google Cloud

## 19.3 Error `403 The caller does not have permission`

Causa:

- la service account no tiene acceso a la Sheet

Solucion:

- compartir la Sheet fuente y destino con el `client_email`

## 19.4 Error `sin_cambios`

Causa:

- la huella coincide con el estado previo

Solucion:

- borrar `state.json`
- cambiar `STATE_FILE`
- borrar cache en GitHub Actions

## 19.5 Reglas generadas pero no publicadas

Causa:

- reglas por debajo de `MIN_CONFIDENCE_AUTOPUBLISH`

Solucion:

- bajar el umbral
- reprocesar
- revisar si el modelo esta proponiendo patrones demasiado genericos

## 19.6 No se publica nada aunque hubo cambios

Causa:

- todas las reglas quedaron por debajo del umbral

Solucion:

- revisar backup JSON
- bajar umbral
- mejorar prompt o calidad de muestra

## 20. Recomendaciones para escalar a producto de cliente

- separar repositorio por cliente o usar plantilla estandar
- usar una service account por cliente
- usar una API key o proyecto OpenAI segregado
- definir ambiente `dev` y `prod`
- guardar historial de backups
- agregar alertas por mail o Slack
- incorporar aprobacion humana opcional para reglas nuevas
- agregar monitoreo de fallos y costos

## 21. Checklist de entrega a cliente

- repo creado
- service account creada
- APIs habilitadas
- Sheets compartidas
- `.env` validado localmente
- prueba `DRY_RUN` aprobada
- prueba real aprobada
- workflow en GitHub Actions operativo
- secrets cargados
- variables cargadas
- scheduler activo
- manual entregado

## 22. Anexo: comando rapido de instalacion local

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python main.py
```

## 23. Anexo: comando rapido de reproceso

```powershell
Remove-Item .\state.json
python main.py
```

## 24. Anexo: criterio de reutilizacion para nuevos clientes

Campos que normalmente cambian por cliente:

- `SOURCE_SPREADSHEET_ID`
- `SOURCE_SHEET_NAME`
- `RULES_SPREADSHEET_ID`
- `RULES_SHEET_NAME`
- `BANK_CODE`
- `MIN_CONFIDENCE_AUTOPUBLISH`
- `MAX_SAMPLE_ROWS`
- `MAX_RULES`
- frecuencia del scheduler
- service account
- API key de OpenAI

Campos que normalmente se conservan:

- estructura base del repositorio
- logica de hashing
- validacion de esquema
- logica de backup
- flujo de GitHub Actions
