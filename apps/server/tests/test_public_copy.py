from app.services.public_copy import public_travel_copy


def test_public_copy_replaces_internal_operational_sentence():
    fallback = "住进杭州，慢慢体验这座城市的另一面。"
    value = "每一套都包含住宿、酒店服务和一段真实可用的文化体验。库存变化会同步到这里。"
    assert public_travel_copy(value, fallback) == fallback


def test_public_copy_keeps_travel_facing_sentence():
    value = "从良渚看展到湘湖散步，把一段想去的杭州留给周末。"
    assert public_travel_copy(value, "fallback") == value
