from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))
from sample_product import copied_product
from validate_package import validate_package


def codes(product):
    return {item["code"] for item in validate_package({"product": product})["validation"]["errors"]}


class ValidatorTests(unittest.TestCase):
    def test_valid_package_passes(self):
        result = validate_package({"product": copied_product()})
        self.assertTrue(result["ok"])

    def test_each_required_error_code_is_stable(self):
        cases = []
        item = copied_product(); item["components"][2]["approved"] = False; cases.append(("RESOURCE_NOT_APPROVED", item))
        item = copied_product(); item["components"][2]["status"] = "UNAVAILABLE"; cases.append(("RESOURCE_UNAVAILABLE", item))
        item = copied_product(); item["components"][2]["remaining"] = 1; cases.append(("CAPACITY_INSUFFICIENT", item))
        item = copied_product(); item["finance"]["gross_margin_rate"] = 0.1; cases.append(("MARGIN_TOO_LOW", item))
        item = copied_product(); item["components"].append({"id": "PR002", "kind": "PARTNER_RESOURCE", "remaining": 4, "quantity_per_package": 2, "approved": True, "status": "AVAILABLE", "exclusive": True, "time_window": "15:30-16:30", "weather_tags": ["小雨"]}); cases.append(("TIME_CONFLICT", item))
        item = copied_product(); item["components"][2]["weather_tags"] = ["晴"]; cases.append(("WEATHER_MISMATCH", item))
        item = copied_product(); item["child_age"] = 5; cases.append(("AGE_NOT_ALLOWED", item))
        item = copied_product(); del item["finance"]; cases.append(("MISSING_REQUIRED_DATA", item))
        for expected, product in cases:
            with self.subTest(expected=expected):
                self.assertIn(expected, codes(product))


if __name__ == "__main__":
    unittest.main()
