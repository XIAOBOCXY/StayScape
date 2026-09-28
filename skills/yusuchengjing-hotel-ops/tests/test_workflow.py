from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_workflow import generate_products


class WorkflowTests(unittest.TestCase):
    def test_generates_distinct_pass_candidates_from_local_facts(self):
        result = generate_products(target_date="2026-09-12", count=2)
        products = [item for item in result["candidates"] if item.get("validation", {}).get("status") == "PASS"]
        self.assertEqual(2, len(products))
        self.assertNotEqual(products[0]["target_segment"], products[1]["target_segment"])
        family = next(item for item in products if item["target_segment"] == "亲子家庭")
        self.assertEqual("R002", family["room_id"])
        self.assertTrue(all(item["recommended_route"][0]["kind"] == "PUBLIC_ROUTE_SUGGESTION" for item in products))


if __name__ == "__main__":
    unittest.main()
