from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from calculate_finance import calculate_finance


class FinanceTests(unittest.TestCase):
    def test_margin_floor_wins_when_higher_than_room_floor(self):
        result = calculate_finance({"total_cost": 480, "room_min_sell_price": 500, "minimum_margin_rate": "0.25", "preferred_price": 520})
        self.assertEqual("640.00", result["minimum_valid_price"])
        self.assertEqual("640.00", result["suggested_price"])

    def test_room_floor_wins_when_higher(self):
        result = calculate_finance({"total_cost": 300, "room_min_sell_price": 500, "minimum_margin_rate": "0.2", "preferred_price": 400})
        self.assertEqual("500.00", result["minimum_valid_price"])
        self.assertEqual("500.00", result["suggested_price"])


if __name__ == "__main__":
    unittest.main()
