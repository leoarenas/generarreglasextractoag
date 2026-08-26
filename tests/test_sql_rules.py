import unittest

from sql_rules import deduplicate_rules, quote_table_name, synchronize_active_rules


class FakeCursor:
    def __init__(self, active_keys):
        self.active_keys = active_keys
        self.executions = []
        self.rowcount = 0

    def execute(self, sql, *params):
        self.executions.append((sql, params))
        if sql.startswith("SET TRANSACTION"):
            self.rowcount = 0
        elif sql.startswith("SELECT"):
            self.rowcount = len(self.active_keys)
        elif sql.startswith("UPDATE") and "[priority]" in sql:
            self.rowcount = 1 if params[-2:] == ("contains", "EXISTENTE") else 0
        else:
            self.rowcount = 1
        return self

    def fetchall(self):
        return list(self.active_keys)

    def close(self):
        pass


class FakeConnection:
    def __init__(self, active_keys=()):
        self.fake_cursor = FakeCursor(active_keys)
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.fake_cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def rule(pattern):
    return {
        "bank_code": "macro",
        "priority": 1,
        "is_active": True,
        "match_type": "contains",
        "pattern": pattern,
        "description_norm": "descripcion",
        "tx_type": "debito",
        "entity_hint": "entidad",
        "confidence_score": 0.95,
        "notes": "nota",
    }


class SqlRulesTests(unittest.TestCase):
    def test_deduplicates_by_business_key_using_lowest_priority(self):
        low_priority = rule("DUP")
        low_priority["priority"] = 9
        high_priority = rule("DUP")
        high_priority["priority"] = 4
        result = deduplicate_rules([low_priority, high_priority])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["priority"], 4)

    def test_quotes_only_schema_and_table_identifiers(self):
        self.assertEqual(quote_table_name("dbo.bank_pattern_rules"), "[dbo].[bank_pattern_rules]")
        with self.assertRaises(ValueError):
            quote_table_name("dbo.rules; DROP TABLE x")

    def test_updates_inserts_and_deactivates_in_one_commit(self):
        connection = FakeConnection(
            [("contains", "EXISTENTE"), ("equals", "AUSENTE")]
        )
        result = synchronize_active_rules(
            connection,
            "dbo.bank_pattern_rules",
            "macro",
            [rule("EXISTENTE"), rule("NUEVA")],
        )
        self.assertEqual((result.inserted, result.updated, result.deactivated), (1, 1, 1))
        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        sql_text = "\n".join(sql for sql, _ in connection.fake_cursor.executions)
        self.assertIn("SET [is_active] = 0", sql_text)
        self.assertIn("INSERT INTO [dbo].[bank_pattern_rules]", sql_text)

    def test_rejects_duplicate_business_keys(self):
        with self.assertRaisesRegex(ValueError, "duplicadas"):
            synchronize_active_rules(
                FakeConnection(),
                "dbo.bank_pattern_rules",
                "macro",
                [rule("DUP"), rule("DUP")],
            )


if __name__ == "__main__":
    unittest.main()
