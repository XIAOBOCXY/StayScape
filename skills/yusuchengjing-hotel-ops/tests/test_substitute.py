from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from common import load_json
from find_substitute import find_substitute


class SubstituteTests(unittest.TestCase):
    def test_unapproved_and_weather_incompatible_resources_are_not_selected(self):
        result = find_substitute(load_json(ROOT / "data" / "partner_resources.json"), {
            "failed_resource_id": "PR001", "date": "2026-09-12", "target_segment": "情侣/双人客",
            "party_size": 2, "weather": "小雨", "max_settlement_price": 80,
        })
        identifiers = {item["resource"]["resource_id"] for item in result["candidates"]}
        self.assertIn("PR004", identifiers)
        self.assertNotIn("PR003", identifiers)
        self.assertNotIn("PR006", identifiers)


if __name__ == "__main__":
    unittest.main()
