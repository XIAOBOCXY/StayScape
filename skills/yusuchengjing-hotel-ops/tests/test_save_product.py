from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from common import ToolFailure
from save_product import save_product


class SaveTests(unittest.TestCase):
    def test_rejects_non_pass_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ToolFailure) as raised:
                save_product({"product_id": "P1", "validation": {"status": "FAIL"}}, Path(directory) / "products.json")
            self.assertEqual("VALIDATION_NOT_PASS", raised.exception.code)

    def test_saves_pass_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "products.json"
            result = save_product({"product_id": "P1", "validation": {"status": "PASS"}}, path)
            self.assertTrue(result["saved"])
            self.assertEqual("P1", json.loads(path.read_text(encoding="utf-8"))["products"][0]["product_id"])


if __name__ == "__main__":
    unittest.main()
