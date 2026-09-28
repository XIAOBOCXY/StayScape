from __future__ import annotations

from copy import deepcopy


def valid_product():
    return {
        "room_id": "R001",
        "target_segment": "情侣/双人客",
        "party_size": 2,
        "weather": "小雨",
        "components": [
            {"id": "R001", "kind": "ROOM", "name": "房间", "remaining": 5, "quantity_per_package": 1, "approved": True, "status": "AVAILABLE", "max_guests": 2},
            {"id": "HS001", "kind": "HOTEL_SERVICE", "name": "早餐", "remaining": 10, "quantity_per_package": 2, "approved": True, "status": "AVAILABLE", "exclusive": False, "time_window": "07:00-10:00"},
            {"id": "PR001", "kind": "PARTNER_RESOURCE", "name": "室内体验", "remaining": 6, "quantity_per_package": 2, "approved": True, "status": "AVAILABLE", "exclusive": True, "time_window": "15:00-16:00", "weather_tags": ["小雨", "暴雨"], "min_age": 6},
        ],
        "capacity": {"max_sellable": 3},
        "finance": {"gross_margin_rate": 0.3, "minimum_margin_rate": 0.25},
    }


def copied_product():
    return deepcopy(valid_product())
