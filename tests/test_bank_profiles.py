import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from bank_profiles import (
    detect_header_row,
    extract_table,
    infer_mapping,
    normalize_rows,
    normalized_file_rows,
    read_tabular_file,
    run_setup_wizard,
    save_profile,
    validate_mapping,
)


class BankProfilesTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "profile_name": "Macro 1234 ARS",
            "account": {
                "bank_name": "Banco Macro",
                "bank_code": "banco_macro",
                "number": "1234",
                "type": "Cuenta corriente",
                "currency": "ARS",
            },
            "format": {"file_type": "csv", "sheet_name": None, "header_row": 3},
            "columns": {
                "Fecha": "fecha_movimiento",
                "Concepto": "descripcion",
                "Debitos": "debito",
                "Creditos": "credito",
                "Referencia": "referencia",
            },
            "normalization": {"decimal_separator": ",", "thousands_separator": "."},
        }

    def test_detects_header_and_mapping(self):
        rows = [["Banco Macro"], ["Cuenta 1234"], ["Fecha", "Concepto", "Debitos", "Creditos"]]
        index = detect_header_row(rows)
        self.assertEqual(index, 2)
        mapping = infer_mapping(rows[index])
        self.assertEqual(mapping["Fecha"], "fecha_movimiento")
        self.assertEqual(mapping["Concepto"], "descripcion")
        self.assertEqual(mapping["Debitos"], "debito")

    def test_requires_identity_and_minimum_mapping(self):
        validate_mapping(self.profile["columns"])
        incomplete = {"Fecha": "fecha_movimiento", "Importe": "importe"}
        with self.assertRaisesRegex(ValueError, "descripcion"):
            validate_mapping(incomplete)

    def test_normalizes_separate_debit_and_credit(self):
        headers = list(self.profile["columns"])
        data = [
            ["01/07/2026", "COMISION", "1.250,50", "", "A1"],
            ["02/07/2026", "TRANSFERENCIA", "", "2.000,00", "A2"],
        ]
        result = normalize_rows(headers, data, self.profile)
        self.assertEqual(result[0]["importe"], -1250.5)
        self.assertEqual(result[0]["tipo_movimiento"], "debito")
        self.assertEqual(result[1]["importe"], 2000.0)
        self.assertEqual(result[1]["moneda"], "ARS")
        self.assertEqual(result[1]["cuenta"], "1234")

    def test_saves_versioned_profiles(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            first = save_profile(dict(self.profile), directory)
            second = save_profile(dict(self.profile), directory)
            self.assertTrue(first.name.endswith("_v1.json"))
            self.assertTrue(second.name.endswith("_v2.json"))
            saved = json.loads(first.read_text(encoding="utf-8"))
            self.assertEqual(saved["account"]["currency"], "ARS")

    def test_reuses_profile_for_a_new_file(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "extracto.csv"
            source.write_text(
                "Banco Macro;;;;\nCuenta 1234;;;;\n"
                "Fecha;Concepto;Debitos;Creditos;Referencia\n"
                "01/07/2026;COMISION;1.250,50;;A1\n",
                encoding="utf-8",
            )
            rows = normalized_file_rows(source, self.profile)
            self.assertEqual(rows[0][0], "fecha_movimiento")
            self.assertEqual(rows[1][2], "COMISION")
            self.assertEqual(rows[1][3], "-1250.5")

    def test_rejects_changed_format(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "extracto.csv"
            source.write_text(
                "Banco Macro;;;\nCuenta 1234;;;\n"
                "Fecha;Detalle;Debitos;Creditos\n"
                "01/07/2026;COMISION;1.250,50;\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "formato cambio"):
                normalized_file_rows(source, self.profile)

    def test_reads_table_from_pdf(self):
        page = MagicMock()
        page.extract_tables.return_value = [
            [["Fecha", "Concepto", "Importe"], ["01/07/2026", "COMISION", "-10,00"]]
        ]
        document = MagicMock()
        document.pages = [page]
        context = MagicMock()
        context.__enter__.return_value = document
        with patch("pdfplumber.open", return_value=context):
            rows, sheet = read_tabular_file(Path("extracto.pdf"))
        self.assertIsNone(sheet)
        self.assertEqual(rows[0], ["Fecha", "Concepto", "Importe"])

    def test_wizard_requests_expanded_account_information(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "extracto.csv"
            source.write_text(
                "Fecha;Concepto;Importe\n01/07/2026;COMISION;-10,00\n",
                encoding="utf-8",
            )
            answers = iter(
                [
                    "Banco Macro",
                    "1234",
                    "Cuenta corriente",
                    "ARS",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "si",
                ]
            )
            prompts = []

            def fake_input(prompt):
                prompts.append(prompt)
                return next(answers)

            target = run_setup_wizard(source, Path(temp) / "profiles", fake_input)
            self.assertTrue(target.exists())
            all_prompts = " ".join(prompts)
            self.assertIn("ultimos 4 caracteres", all_prompts)
            self.assertIn("Cuenta corriente", all_prompts)


if __name__ == "__main__":
    unittest.main()
