from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from calculate_capacity import calculate_capacity


class CapacityTests(unittest.TestCase):
    def test_room_can_be_bottleneck(self):
        result = calculate_capacity({"components": [{"id": "R", "kind": "ROOM", "remaining": 2, "quantity_per_package": 1}, {"id": "S", "kind": "HOTEL_SERVICE", "remaining": 10, "quantity_per_package": 1}]})
        self.assertEqual("R", result["bottleneck_resource"]["id"])

    def test_service_can_be_bottleneck(self):
        result = calculate_capacity({"components": [{"id": "R", "kind": "ROOM", "remaining": 10, "quantity_per_package": 1}, {"id": "S", "kind": "HOTEL_SERVICE", "remaining": 3, "quantity_per_package": 2}]})
        self.assertEqual("S", result["bottleneck_resource"]["id"])

    def test_partner_can_be_bottleneck(self):
        result = calculate_capacity({"components": [{"id": "R", "kind": "ROOM", "remaining": 10, "quantity_per_package": 1}, {"id": "P", "kind": "PARTNER_RESOURCE", "remaining": 5, "quantity_per_package": 2, "approved": True}]})
        self.assertEqual("P", result["bottleneck_resource"]["id"])
        self.assertEqual(2, result["max_sellable"])


if __name__ == "__main__":
    unittest.main()
