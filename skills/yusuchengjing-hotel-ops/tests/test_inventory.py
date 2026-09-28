from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_inventory import analyze_inventory
from common import load_json


class InventoryTests(unittest.TestCase):
    def test_high_remaining_and_slow_velocity_rank_first(self):
        result = analyze_inventory(load_json(ROOT / "data" / "room_inventory.json"))
        self.assertTrue(result["ok"])
        self.assertEqual("R001", result["priority_room_id"])
        self.assertEqual(1, result["rooms"][0]["priority_rank"])


if __name__ == "__main__":
    unittest.main()
