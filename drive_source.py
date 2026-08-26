import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xlsm", ".pdf"}
GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True)
class DriveSourceFile:
    file_id: str
    name: str
    modified_time: str
    mime_type: str


def load_drive_sources(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    banks = payload.get("banks")
    if not isinstance(banks, list) or not banks:
        raise ValueError("La configuracion multibanco no contiene una lista 'banks'.")
    enabled = []
    for bank in banks:
        missing = [
            field
            for field in ("bank_code", "bank_name", "drive_folder_id", "profiles")
            if not bank.get(field)
        ]
        if missing:
            raise ValueError(
                f"Configuracion incompleta para un banco. Faltan: {', '.join(missing)}"
            )
        if bank.get("enabled", True):
            enabled.append(bank)
    if not enabled:
        raise ValueError("No hay bancos habilitados en la configuracion multibanco.")
    return enabled


def is_supported_file(item: dict[str, Any]) -> bool:
    return (
        item.get("mimeType") == GOOGLE_SHEET_MIME
        or Path(item.get("name", "")).suffix.lower() in SUPPORTED_EXTENSIONS
    )


def select_latest_file(
    files: list[dict[str, Any]], name_pattern: str = "*"
) -> DriveSourceFile:
    candidates = [
        item
        for item in files
        if is_supported_file(item)
        and fnmatch.fnmatch(item.get("name", "").lower(), name_pattern.lower())
    ]
    if not candidates:
        raise ValueError(
            "No se encontraron archivos compatibles en la carpeta de Google Drive "
            f"para el patron '{name_pattern}'."
        )
    latest = max(candidates, key=lambda item: item.get("modifiedTime", ""))
    return DriveSourceFile(
        file_id=latest["id"],
        name=latest["name"],
        modified_time=latest["modifiedTime"],
        mime_type=latest["mimeType"],
    )


def list_folder_files(service: Any, folder_id: str) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    page_token = None
    while True:
        response = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="nextPageToken, files(id,name,mimeType,modifiedTime)",
                orderBy="modifiedTime desc",
                pageSize=1000,
                pageToken=page_token,
            )
            .execute()
        )
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return files


def download_drive_file(service: Any, source: DriveSourceFile, target_dir: Path) -> Path:
    try:
        from googleapiclient.http import MediaIoBaseDownload
    except ImportError as exc:
        raise RuntimeError(
            "Instale google-api-python-client para descargar archivos desde Drive."
        ) from exc

    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(source.name).name
    if source.mime_type == GOOGLE_SHEET_MIME:
        safe_name = f"{safe_name}.xlsx" if not safe_name.lower().endswith(".xlsx") else safe_name
        request = service.files().export_media(fileId=source.file_id, mimeType=XLSX_MIME)
    else:
        request = service.files().get_media(fileId=source.file_id)
    target = target_dir / f"{source.file_id}_{safe_name}"
    with target.open("wb") as output:
        downloader = MediaIoBaseDownload(output, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    return target


def fetch_latest_drive_file(
    service: Any,
    folder_id: str,
    name_pattern: str,
    target_dir: Path,
) -> tuple[DriveSourceFile, Path]:
    source = select_latest_file(list_folder_files(service, folder_id), name_pattern)
    return source, download_drive_file(service, source, target_dir)
