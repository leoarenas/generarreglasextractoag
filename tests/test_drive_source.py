import json
import tempfile
import unittest
from pathlib import Path

from drive_source import GOOGLE_SHEET_MIME, load_drive_sources, select_latest_file


class DriveSourceTests(unittest.TestCase):
    def test_selects_latest_supported_file_by_modified_time(self):
        files = [
            {
                "id": "old",
                "name": "extracto_2026_06.pdf",
                "mimeType": "application/pdf",
                "modifiedTime": "2026-07-01T10:00:00Z",
            },
            {
                "id": "new",
                "name": "extracto_2026_07.pdf",
                "mimeType": "application/pdf",
                "modifiedTime": "2026-07-25T10:00:00Z",
            },
            {
                "id": "ignored",
                "name": "notas.txt",
                "mimeType": "text/plain",
                "modifiedTime": "2026-07-28T10:00:00Z",
            },
        ]
        selected = select_latest_file(files)
        self.assertEqual(selected.file_id, "new")

    def test_applies_case_insensitive_name_pattern(self):
        files = [
            {
                "id": "macro",
                "name": "E-Resumen Macro Julio.PDF",
                "mimeType": "application/pdf",
                "modifiedTime": "2026-07-25T10:00:00Z",
            },
            {
                "id": "other",
                "name": "Otro Banco Julio.pdf",
                "mimeType": "application/pdf",
                "modifiedTime": "2026-07-27T10:00:00Z",
            },
        ]
        selected = select_latest_file(files, "*macro*.pdf")
        self.assertEqual(selected.file_id, "macro")

    def test_accepts_native_google_sheet(self):
        selected = select_latest_file(
            [
                {
                    "id": "sheet",
                    "name": "Extracto",
                    "mimeType": GOOGLE_SHEET_MIME,
                    "modifiedTime": "2026-07-25T10:00:00Z",
                }
            ]
        )
        self.assertEqual(selected.file_id, "sheet")

    def test_fails_when_folder_has_no_compatible_file(self):
        with self.assertRaisesRegex(ValueError, "No se encontraron"):
            select_latest_file(
                [
                    {
                        "id": "text",
                        "name": "notas.txt",
                        "mimeType": "text/plain",
                        "modifiedTime": "2026-07-25T10:00:00Z",
                    }
                ]
            )

    def test_loads_only_enabled_bank_sources(self):
        payload = {
            "version": 1,
            "banks": [
                {
                    "bank_code": "macro",
                    "bank_name": "Banco Macro",
                    "enabled": True,
                    "drive_folder_id": "folder",
                    "profiles": ["profile.json"],
                },
                {
                    "bank_code": "disabled",
                    "bank_name": "Deshabilitado",
                    "enabled": False,
                    "drive_folder_id": "other",
                    "profiles": ["other.json"],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sources.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            sources = load_drive_sources(path)
        self.assertEqual([source["bank_code"] for source in sources], ["macro"])


if __name__ == "__main__":
    unittest.main()
