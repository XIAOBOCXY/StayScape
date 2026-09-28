from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_demand import analyze_demand
from common import load_json


class DemandTests(unittest.TestCase):
    def test_funnel_score_is_ranked_and_explainable(self):
        result = analyze_demand(load_json(ROOT / "data" / "recent_sales.json"))
        self.assertEqual("情侣/双人客", result["priority_segment"])
        self.assertGreater(result["segments"][0]["demand_score"], result["segments"][-1]["demand_score"])
        self.assertIn("booking_rate", result["segments"][0])


if __name__ == "__main__":
    unittest.main()
