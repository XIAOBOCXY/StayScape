"""Curated, attributable travel knowledge for the Hangzhou hotel assistant."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import TravelKnowledge


# These records intentionally distinguish a sourced fact from a recommendation.
# Any field whose source has not been freshly rechecked is marked
# VERIFY_REQUIRED, which prevents the Agent from presenting it as a promise.
CURATED_HANGZHOU_KNOWLEDGE: tuple[dict[str, Any], ...] = (
    {
        "slug": "west-lake-scenic-area",
        "name": "西湖风景名胜区",
        "category": "CITY_WALK",
        "area": "西湖区",
        "address": "杭州市西湖风景名胜区",
        "indoor_outdoor": "OUTDOOR",
        "suitable_crowds": "FAMILY,COUPLE,FRIENDS,SOLO,LOCAL_WEEKEND",
        "suggested_duration_minutes": 120,
        "opening_hours": "开放式景区；具体场点开放、交通管理与预约要求以当天官方公告为准。",
        "weather_adaptations": "SUNNY,CLOUDY",
        "reservation_notice": "旺季、长假和大客流时段可能有分时段交通管理或预约安排。",
        "description": "适合湖畔步行、城市摄影和慢节奏公共空间体验。",
        "source_name": "杭州市人民政府公报 / 西湖景区管理通告",
        "source_url": "https://zfgb.hangzhou.gov.cn/11/105220253/t117220253054/518894.shtml",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "china-national-silk-museum",
        "name": "中国丝绸博物馆",
        "category": "MUSEUM",
        "area": "西湖区",
        "address": "杭州市西湖区玉皇山路73-1号",
        "indoor_outdoor": "INDOOR",
        "suitable_crowds": "FAMILY,COUPLE,FRIENDS,SOLO,LOCAL_WEEKEND",
        "suggested_duration_minutes": 120,
        "opening_hours": "来源公告记载：周二至周日 9:00-17:00，16:30 停止入馆；周一闭馆（节假日安排以官方最新公告为准）。",
        "weather_adaptations": "RAIN,CLOUDY,SUNNY",
        "reservation_notice": "来源公告记载普通参观无需提前预约；讲解、特展和临时活动请以官方预约页面为准。",
        "description": "以丝绸纺织服饰文化遗产为主题的国家一级博物馆，适合雨天和人文主题行程。",
        "source_name": "中国丝绸博物馆官网",
        "source_url": "https://www.chinasilkmuseum.com/cgjyy/info_6.aspx?itemid=31249",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "zhejiang-museum-gushan",
        "name": "浙江省博物馆孤山馆区",
        "category": "MUSEUM",
        "area": "西湖区",
        "address": "杭州市西湖区孤山路25号",
        "indoor_outdoor": "INDOOR",
        "suitable_crowds": "FAMILY,COUPLE,FRIENDS,SOLO,LOCAL_WEEKEND",
        "suggested_duration_minutes": 120,
        "opening_hours": "请以浙江省博物馆官方最新开放公告为准。",
        "weather_adaptations": "RAIN,CLOUDY,SUNNY",
        "reservation_notice": "特展、团体和节假日规则可能不同，请在官方渠道确认。",
        "description": "适合以浙江历史、文博看展和西湖文化为主题的室内体验。",
        "source_name": "浙江省博物馆官网",
        "source_url": "https://www.zhejiangmuseum.com/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "liangzhu-museum",
        "name": "良渚博物院",
        "category": "MUSEUM",
        "area": "余杭区良渚",
        "address": "杭州市余杭区良渚街道美丽洲路1号",
        "indoor_outdoor": "INDOOR",
        "suitable_crowds": "FAMILY,COUPLE,FRIENDS,SOLO,LOCAL_WEEKEND",
        "suggested_duration_minutes": 150,
        "opening_hours": "请以良渚遗址与博物院官方最新开放公告为准。",
        "weather_adaptations": "RAIN,CLOUDY,SUNNY",
        "reservation_notice": "节假日、讲解和临展可能需要预约或分时入场，请先核验。",
        "description": "以良渚文明为线索的文博参观方向，适合亲子历史启蒙与人文主题行程。",
        "source_name": "杭州良渚遗址管理区官方信息",
        "source_url": "https://www.liangzhu.gov.cn/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "china-cartoon-animation-museum",
        "name": "中国动漫博物馆",
        "category": "MUSEUM",
        "area": "滨江区",
        "address": "杭州市滨江区白马湖路375号",
        "indoor_outdoor": "INDOOR",
        "suitable_crowds": "FAMILY,FRIENDS,SOLO,LOCAL_WEEKEND",
        "minimum_age": 3,
        "suggested_duration_minutes": 150,
        "opening_hours": "请以中国动漫博物馆官方预约页面的最新开放安排为准。",
        "weather_adaptations": "RAIN,CLOUDY,SUNNY",
        "reservation_notice": "建议提前确认场次、特展和入馆要求。",
        "description": "以动画、漫画与互动展陈为主题的室内文博空间，适合亲子和朋友同行。",
        "source_name": "中国动漫博物馆官网",
        "source_url": "https://www.cacm.org.cn/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "zhejiang-natural-history-museum",
        "name": "浙江自然博物院杭州馆",
        "category": "MUSEUM",
        "area": "拱墅区",
        "address": "杭州市拱墅区西湖文化广场6号",
        "indoor_outdoor": "INDOOR",
        "suitable_crowds": "FAMILY,FRIENDS,SOLO,LOCAL_WEEKEND",
        "minimum_age": 3,
        "suggested_duration_minutes": 150,
        "opening_hours": "请以浙江自然博物院官方最新开放公告为准。",
        "weather_adaptations": "RAIN,CLOUDY,SUNNY",
        "reservation_notice": "临展、教育活动和节假日参观规则请先核验。",
        "description": "适合亲子科学探索、自然主题看展和雨天室内行程。",
        "source_name": "浙江自然博物院官网",
        "source_url": "https://www.zmnh.com/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "hangzhou-museum",
        "name": "杭州博物馆",
        "category": "MUSEUM",
        "area": "上城区",
        "address": "杭州市上城区粮道山18号",
        "indoor_outdoor": "INDOOR",
        "suitable_crowds": "FAMILY,COUPLE,FRIENDS,SOLO,LOCAL_WEEKEND",
        "suggested_duration_minutes": 90,
        "opening_hours": "请以杭州博物馆官方最新开放公告为准。",
        "weather_adaptations": "RAIN,CLOUDY,SUNNY",
        "reservation_notice": "展览、讲解与入馆规则请以官方预约渠道为准。",
        "description": "适合城市历史、南宋文化和短时室内看展安排。",
        "source_name": "杭州博物馆官网",
        "source_url": "https://www.hangzhoumuseum.com/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "xixi-wetland",
        "name": "西溪国家湿地公园",
        "category": "NATURE",
        "area": "西湖区",
        "address": "杭州市西湖区天目山路518号",
        "indoor_outdoor": "OUTDOOR",
        "suitable_crowds": "FAMILY,COUPLE,FRIENDS,SOLO,LOCAL_WEEKEND",
        "suggested_duration_minutes": 180,
        "opening_hours": "请以西溪湿地官方最新开放和票务公告为准。",
        "weather_adaptations": "SUNNY,CLOUDY",
        "reservation_notice": "雨天、季节活动、船次及票务安排需在出行前确认。",
        "description": "适合自然观察、亲子探索和低强度户外漫游。",
        "source_name": "西溪湿地官方信息",
        "source_url": "https://www.xixishidi.com/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "songcheng",
        "name": "杭州宋城",
        "category": "PERFORMANCE",
        "area": "西湖区",
        "address": "杭州市西湖区之江路148号",
        "indoor_outdoor": "MIXED",
        "suitable_crowds": "FAMILY,COUPLE,FRIENDS,LOCAL_WEEKEND",
        "suggested_duration_minutes": 240,
        "opening_hours": "演出与园区开放时间以杭州宋城官方当日场次为准。",
        "weather_adaptations": "RAIN,CLOUDY,SUNNY",
        "reservation_notice": "演出票、入园时段和儿童规则需在官方购票页确认。",
        "description": "适合演艺、主题乐园和夜间体验方向，不能将场次视为固定事实。",
        "source_name": "宋城演艺官方渠道",
        "source_url": "https://www.songcn.com/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "hangzhou-botanical-garden",
        "name": "杭州植物园",
        "category": "NATURE",
        "area": "西湖区",
        "address": "杭州市西湖区桃源岭1号",
        "indoor_outdoor": "OUTDOOR",
        "suitable_crowds": "FAMILY,COUPLE,FRIENDS,SOLO,LOCAL_WEEKEND",
        "suggested_duration_minutes": 120,
        "opening_hours": "请以杭州植物园官方最新开放公告为准。",
        "weather_adaptations": "SUNNY,CLOUDY",
        "reservation_notice": "花展、活动日和天气原因可能影响安排，请先确认。",
        "description": "适合自然观察、植物主题亲子活动和轻量步行。",
        "source_name": "杭州植物园官方信息",
        "source_url": "https://www.hzbg.cn/",
        "verification_status": "VERIFY_REQUIRED",
    },
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def seed_curated_hangzhou(self) -> int:
        """Insert only missing records so hotel-managed review edits survive."""
        created = 0
        now = _utc_now()
        for value in CURATED_HANGZHOU_KNOWLEDGE:
            if self.db.scalar(select(TravelKnowledge).where(TravelKnowledge.slug == value["slug"])):
                continue
            self.db.add(
                TravelKnowledge(
                    **value,
                    verified_at=now,
                    source_updated_at=None,
                    status="ACTIVE",
                )
            )
            created += 1
        if created:
            self.db.flush()
        return created

    @staticmethod
    def _record_status(item: TravelKnowledge) -> str:
        if item.status != "ACTIVE":
            return "UNAVAILABLE"
        if item.verification_status != "ACTIVE":
            return "VERIFY_REQUIRED"
        if not item.verified_at:
            return "VERIFY_REQUIRED"
        age = (_utc_now() - item.verified_at).days
        return "ACTIVE" if age <= max(1, settings.knowledge_review_days) else "STALE"

    def to_context(self, item: TravelKnowledge) -> dict[str, Any]:
        status = self._record_status(item)
        opening = item.opening_hours
        reservation = item.reservation_notice
        if status != "ACTIVE":
            confirmation = "信息需确认，请以来源页面的最新公告、票务或预约规则为准。"
            opening = f"{opening} {confirmation}".strip()
            reservation = f"{reservation} {confirmation}".strip()
        return {
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "area": item.area,
            "address": item.address,
            "indoor_outdoor": item.indoor_outdoor,
            "suitable_crowds": item.suitable_crowds,
            "minimum_age": item.minimum_age,
            "maximum_age": item.maximum_age,
            "suggested_duration_minutes": item.suggested_duration_minutes,
            "opening_hours": opening,
            "weather_adaptations": item.weather_adaptations,
            "reservation_notice": reservation,
            "description": item.description,
            "source_name": item.source_name,
            "source_url": item.source_url,
            "source_updated_at": item.source_updated_at.isoformat() if item.source_updated_at else None,
            "verified_at": item.verified_at.isoformat() if item.verified_at else None,
            "verification_status": status,
            "bookable": False,
        }

    def search(self, query: str = "", *, target_crowd: str = "", weather: str = "", limit: int = 8) -> list[dict[str, Any]]:
        items = list(
            self.db.scalars(
                select(TravelKnowledge)
                .where(TravelKnowledge.status == "ACTIVE")
                .order_by(TravelKnowledge.name)
            ).all()
        )
        words = [word.lower() for word in query.replace("，", " ").replace("、", " ").split() if word.strip()]

        def score(item: TravelKnowledge) -> int:
            haystack = f"{item.name} {item.category} {item.area} {item.description}".lower()
            result = sum(5 for word in words if word in haystack)
            if target_crowd and (target_crowd in item.suitable_crowds or "ALL" in item.suitable_crowds):
                result += 2
            if weather and weather in item.weather_adaptations:
                result += 1
            if item.indoor_outdoor == "INDOOR" and weather == "RAIN":
                result += 2
            return result

        ranked = sorted(items, key=lambda item: (score(item), item.name), reverse=True)
        if words:
            matched = [item for item in ranked if score(item) > 0]
            ranked = matched or ranked
        return [self.to_context(item) for item in ranked[: max(1, min(limit, 20))]]
