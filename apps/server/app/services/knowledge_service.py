"""Curated, attributable travel knowledge for the Hangzhou hotel assistant."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import TravelKnowledge
from .knowledge_updates import KNOWLEDGE_ADDITIONS, KNOWLEDGE_EXPANSION, KNOWLEDGE_FIELD_UPDATES


# Enum-ish codes are never shown to operators or visitors: every page reads the
# Chinese label from these maps (or from the *_label fields in API responses).
CATEGORY_LABELS = {
    "MUSEUM": "博物馆",
    "ART_MUSEUM": "美术馆",
    "SCIENCE_MUSEUM": "科技馆",
    "LIBRARY": "图书馆",
    "CITY_WALK": "城市漫步",
    "NATURE": "自然湿地",
    "FAMILY_PARK": "亲子公园",
    "THEME_PARK": "主题乐园",
    "PERFORMANCE": "演出剧场",
    "NIGHTLIFE": "夜游",
    "FOOD": "美食街区",
    "WORKSHOP": "手作工坊",
    "SPORT": "运动体验",
    "PARK": "遗址公园",
}
CROWD_LABELS = {
    "FAMILY": "亲子家庭",
    "COUPLE": "两人同行",
    "FRIENDS": "朋友出行",
    "SOLO": "独自旅行",
    "LOCAL_WEEKEND": "本地周末",
    "ALL": "不限客群",
}
WEATHER_LABELS = {"RAIN": "雨天", "CLOUDY": "多云", "SUNNY": "晴天"}
INDOOR_LABELS = {"INDOOR": "室内", "OUTDOOR": "户外", "MIXED": "室内外皆可"}


def label_category(value: object) -> str:
    text = str(value or "").strip()
    return CATEGORY_LABELS.get(text, text or "未分类")


def label_crowds(value: object) -> str:
    parts = [part.strip() for part in str(value or "").replace("，", ",").split(",") if part.strip()]
    return "、".join(CROWD_LABELS.get(part.upper(), part) for part in parts) or "不限客群"


def label_weather(value: object) -> str:
    parts = [part.strip() for part in str(value or "").split(",") if part.strip()]
    return "、".join(WEATHER_LABELS.get(part.upper(), part) for part in parts) or "不限天气"


def label_indoor(value: object) -> str:
    return INDOOR_LABELS.get(str(value or "").strip().upper(), "室内外皆可")


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
    {
        "slug": "zhejiang-art-museum",
        "name": "浙江美术馆",
        "category": "ART_MUSEUM",
        "area": "西湖区",
        "address": "杭州市西湖区南山路138号",
        "indoor_outdoor": "INDOOR",
        "suitable_crowds": "COUPLE,FRIENDS,SOLO,LOCAL_WEEKEND",
        "suggested_duration_minutes": 120,
        "opening_hours": "请以浙江美术馆官方展览与开放公告为准。",
        "weather_adaptations": "RAIN,CLOUDY,SUNNY",
        "reservation_notice": "不同展览和活动的预约规则可能不同，请先确认。",
        "description": "适合艺术看展、双人慢游和城市周末的人文路线。",
        "source_name": "浙江美术馆官网",
        "source_url": "https://www.zjam.org.cn/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "china-academy-art-museum",
        "name": "中国美术学院美术馆",
        "category": "ART_MUSEUM",
        "area": "上城区",
        "address": "杭州市上城区南山路218号",
        "indoor_outdoor": "INDOOR",
        "suitable_crowds": "COUPLE,FRIENDS,SOLO,LOCAL_WEEKEND",
        "suggested_duration_minutes": 120,
        "opening_hours": "请以中国美术学院与美术馆官方公告为准。",
        "weather_adaptations": "RAIN,CLOUDY,SUNNY",
        "reservation_notice": "展览开放、入场与活动规则请先核验。",
        "description": "适合当代艺术、设计与看展主题的室内城市体验。",
        "source_name": "中国美术学院官网",
        "source_url": "https://www.caa.edu.cn/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "zhejiang-science-technology-museum",
        "name": "浙江省科技馆",
        "category": "SCIENCE_MUSEUM",
        "area": "拱墅区",
        "address": "杭州市拱墅区西湖文化广场A区",
        "indoor_outdoor": "INDOOR",
        "suitable_crowds": "FAMILY,FRIENDS,LOCAL_WEEKEND",
        "minimum_age": 3,
        "suggested_duration_minutes": 150,
        "opening_hours": "请以浙江省科技馆官方开放与预约公告为准。",
        "weather_adaptations": "RAIN,CLOUDY,SUNNY",
        "reservation_notice": "教育活动、临展和节假日可能有单独预约要求。",
        "description": "适合亲子科学探索、互动展陈和雨天室内安排。",
        "source_name": "浙江省科技馆官网",
        "source_url": "https://www.zjstm.org.cn/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "china-tea-museum",
        "name": "中国茶叶博物馆双峰馆区",
        "category": "MUSEUM",
        "area": "西湖区",
        "address": "杭州市西湖区龙井路88号",
        "indoor_outdoor": "MIXED",
        "suitable_crowds": "COUPLE,FRIENDS,SOLO,LOCAL_WEEKEND",
        "suggested_duration_minutes": 120,
        "opening_hours": "请以中国茶叶博物馆官方开放公告为准。",
        "weather_adaptations": "CLOUDY,SUNNY",
        "reservation_notice": "馆区活动和讲解服务请以官方渠道确认。",
        "description": "适合茶文化、园林和轻量人文路线；不等同于可售点茶体验。",
        "source_name": "中国茶叶博物馆官网",
        "source_url": "https://www.teamuseum.cn/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "hangzhou-craft-museum-cluster",
        "name": "杭州工艺美术博物馆群",
        "category": "MUSEUM",
        "area": "拱墅区",
        "address": "杭州市拱墅区小河路334号附近",
        "indoor_outdoor": "INDOOR",
        "suitable_crowds": "FAMILY,COUPLE,FRIENDS,SOLO,LOCAL_WEEKEND",
        "suggested_duration_minutes": 120,
        "opening_hours": "请以场馆最新开放公告为准。",
        "weather_adaptations": "RAIN,CLOUDY,SUNNY",
        "reservation_notice": "各馆展览与活动规则可能不同，请先核验。",
        "description": "适合工艺、手作和运河周边人文路线的公共参考。",
        "source_name": "杭州市文化广电旅游局",
        "source_url": "https://wgly.hangzhou.gov.cn/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "grand-canal-hangzhou",
        "name": "京杭大运河杭州段",
        "category": "CITY_WALK",
        "area": "拱墅区",
        "address": "杭州市拱墅区运河沿线",
        "indoor_outdoor": "OUTDOOR",
        "suitable_crowds": "FAMILY,COUPLE,FRIENDS,SOLO,LOCAL_WEEKEND",
        "suggested_duration_minutes": 120,
        "opening_hours": "开放式公共空间，具体场点与水上项目以管理公告为准。",
        "weather_adaptations": "SUNNY,CLOUDY",
        "reservation_notice": "交通、水上项目与沿线场馆安排请以当日公告为准。",
        "description": "适合运河散步、城市摄影和低强度公共空间路线。",
        "source_name": "杭州运河集团",
        "source_url": "https://www.hzcanal.com/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "xiaohezhijie",
        "name": "小河直街历史文化街区",
        "category": "CITY_WALK",
        "area": "拱墅区",
        "address": "杭州市拱墅区小河直街",
        "indoor_outdoor": "OUTDOOR",
        "suitable_crowds": "FAMILY,COUPLE,FRIENDS,SOLO,LOCAL_WEEKEND",
        "suggested_duration_minutes": 90,
        "opening_hours": "开放式街区，商户与展点营业安排以现场为准。",
        "weather_adaptations": "SUNNY,CLOUDY",
        "reservation_notice": "公共街区不是套餐权益；个别商户活动需自行确认。",
        "description": "适合运河周边慢行、街区观察和小体量城市漫游。",
        "source_name": "杭州市文化广电旅游局",
        "source_url": "https://wgly.hangzhou.gov.cn/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "hubin-pedestrian-street",
        "name": "湖滨步行街",
        "category": "CITY_WALK",
        "area": "上城区",
        "address": "杭州市上城区湖滨路周边",
        "indoor_outdoor": "OUTDOOR",
        "suitable_crowds": "FAMILY,COUPLE,FRIENDS,SOLO,LOCAL_WEEKEND",
        "suggested_duration_minutes": 90,
        "opening_hours": "开放式街区，商户营业以现场为准。",
        "weather_adaptations": "SUNNY,CLOUDY",
        "reservation_notice": "客流和交通管理安排请以当日公告为准。",
        "description": "适合餐后散步、城市夜景和公共空间路线。",
        "source_name": "杭州市上城区人民政府",
        "source_url": "https://www.hzsc.gov.cn/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "qinghefang",
        "name": "清河坊历史文化街区",
        "category": "CITY_WALK",
        "area": "上城区",
        "address": "杭州市上城区河坊街",
        "indoor_outdoor": "OUTDOOR",
        "suitable_crowds": "FAMILY,COUPLE,FRIENDS,SOLO,LOCAL_WEEKEND",
        "suggested_duration_minutes": 120,
        "opening_hours": "开放式街区，商户和展点营业以现场为准。",
        "weather_adaptations": "SUNNY,CLOUDY",
        "reservation_notice": "公共街区参观不等同于酒店已包含权益。",
        "description": "适合城市历史、街巷慢游和手作店铺观察。",
        "source_name": "杭州市上城区人民政府",
        "source_url": "https://www.hzsc.gov.cn/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "hangzhou-zoo",
        "name": "杭州动物园",
        "category": "FAMILY_PARK",
        "area": "西湖区",
        "address": "杭州市西湖区虎跑路40号",
        "indoor_outdoor": "OUTDOOR",
        "suitable_crowds": "FAMILY",
        "minimum_age": 3,
        "suggested_duration_minutes": 180,
        "opening_hours": "请以杭州动物园官方开放与预约公告为准。",
        "weather_adaptations": "SUNNY,CLOUDY",
        "reservation_notice": "天气、客流和儿童规则请在出行前确认。",
        "description": "适合亲子自然观察方向，雨天不作为优先正式体验。",
        "source_name": "杭州西湖风景名胜区管理委员会",
        "source_url": "https://westlake.hangzhou.gov.cn/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "hangzhou-wildlife-world",
        "name": "杭州野生动物世界",
        "category": "FAMILY_PARK",
        "area": "富阳区",
        "address": "杭州市富阳区银湖街道九龙大道1号",
        "indoor_outdoor": "OUTDOOR",
        "suitable_crowds": "FAMILY",
        "minimum_age": 3,
        "suggested_duration_minutes": 300,
        "opening_hours": "请以杭州野生动物世界官方开放与购票公告为准。",
        "weather_adaptations": "SUNNY,CLOUDY",
        "reservation_notice": "交通、入园和儿童规则需提前确认。",
        "description": "适合亲子主题乐园方向的远距离公共参考。",
        "source_name": "杭州野生动物世界官网",
        "source_url": "https://www.hzsp.com/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "hangzhou-paradise",
        "name": "杭州乐园",
        "category": "THEME_PARK",
        "area": "萧山区",
        "address": "杭州市萧山区风情大道2555号",
        "indoor_outdoor": "MIXED",
        "suitable_crowds": "FAMILY,COUPLE,FRIENDS",
        "suggested_duration_minutes": 240,
        "opening_hours": "请以杭州乐园官方开放与项目公告为准。",
        "weather_adaptations": "CLOUDY,SUNNY",
        "reservation_notice": "项目开放、票务和身高年龄规则请先确认。",
        "description": "适合乐园、朋友同行和亲子娱乐方向的公共参考。",
        "source_name": "杭州乐园官方渠道",
        "source_url": "https://www.hzparadise.com/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "qianjiang-city-balcony",
        "name": "钱江新城城市阳台",
        "category": "CITY_WALK",
        "area": "上城区",
        "address": "杭州市上城区钱江新城沿江区域",
        "indoor_outdoor": "OUTDOOR",
        "suitable_crowds": "COUPLE,FRIENDS,SOLO,LOCAL_WEEKEND",
        "suggested_duration_minutes": 90,
        "opening_hours": "开放式公共空间，管理安排以当日公告为准。",
        "weather_adaptations": "SUNNY,CLOUDY",
        "reservation_notice": "不作为住宿产品的自动包含权益。",
        "description": "适合江景、城市夜间散步和摄影路线。",
        "source_name": "杭州市上城区人民政府",
        "source_url": "https://www.hzsc.gov.cn/",
        "verification_status": "VERIFY_REQUIRED",
    },
    {
        "slug": "zhejiang-library-zhijiang",
        "name": "浙江图书馆之江馆",
        "category": "LIBRARY",
        "area": "西湖区",
        "address": "杭州市西湖区之江文化中心",
        "indoor_outdoor": "INDOOR",
        "suitable_crowds": "FAMILY,COUPLE,FRIENDS,SOLO,LOCAL_WEEKEND",
        "suggested_duration_minutes": 90,
        "opening_hours": "请以浙江图书馆官方开放与入馆公告为准。",
        "weather_adaptations": "RAIN,CLOUDY,SUNNY",
        "reservation_notice": "展览、活动和入馆规则可能变化，请先核验。",
        "description": "适合阅读、展览和安静的雨天公共路线。",
        "source_name": "浙江图书馆官网",
        "source_url": "https://www.zjlib.cn/",
        "verification_status": "VERIFY_REQUIRED",
    },
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _age_in_days(value: datetime | None) -> int | None:
    """Days since a stored timestamp.

    SQLite (used by the test suite) returns naive datetimes while production
    returns timezone-aware ones.  Normalising here keeps the review-age check
    working in both environments instead of raising on a mixed comparison.
    """

    if value is None:
        return None
    moment = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - moment).days)


# The first version intentionally uses transparent phrase aliases instead of a
# hidden vector search. This makes a sentence such as "想带孩子去博物馆" find
# museum-family records even when the query has no whitespace token boundary.
_QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    "博物馆": ("MUSEUM", "ART_MUSEUM", "SCIENCE_MUSEUM"),
    "看展": ("MUSEUM", "ART_MUSEUM"),
    "美术馆": ("ART_MUSEUM",),
    "科技馆": ("SCIENCE_MUSEUM",),
    "亲子": ("FAMILY",),
    "孩子": ("FAMILY",),
    "儿童": ("FAMILY",),
    "乐园": ("THEME_PARK", "FAMILY_PARK"),
    "游乐": ("THEME_PARK", "FAMILY_PARK"),
    "动漫": ("ANIMATION",),
    "自然": ("NATURE", "FAMILY_PARK"),
    "湿地": ("NATURE",),
    "运河": ("CITY_WALK",),
    "城市漫游": ("CITY_WALK",),
    "夜游": ("CITY_WALK", "PERFORMANCE"),
    "演出": ("PERFORMANCE",),
    "手作": ("CULTURE", "MUSEUM"),
    "雨天": ("INDOOR",),
}


class KnowledgeService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def seed_curated_hangzhou(self) -> int:
        """Sync curated content without claiming operator review.

        Changed facts invalidate prior review; link reachability is transport metadata.
        """

        created = 0
        now = _utc_now()
        for value in (*CURATED_HANGZHOU_KNOWLEDGE, *KNOWLEDGE_ADDITIONS, *KNOWLEDGE_EXPANSION):
            slug = str(value["slug"])
            existing = self.db.scalar(select(TravelKnowledge).where(TravelKnowledge.slug == slug))
            if existing is None:
                record = dict(value)
                record.update(
                    verification_status="VERIFY_REQUIRED",
                    verified_at=None,
                    source_updated_at=None,
                    verified_fields=[],
                    status="ACTIVE",
                )
                self.db.add(TravelKnowledge(**record))
                created += 1
                continue
            update = KNOWLEDGE_FIELD_UPDATES.get(slug, {})
            changed = False
            for field, new_value in update.items():
                if getattr(existing, field, None) != new_value:
                    setattr(existing, field, new_value)
                    changed = True
            if changed:
                existing.verification_status = "VERIFY_REQUIRED"
                existing.verified_at = None
                existing.verified_by_user_id = None
                existing.verification_note = ""
                existing.verified_fields = []
                existing.source_updated_at = None
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
        age = _age_in_days(item.verified_at)
        if age is None:
            return "VERIFY_REQUIRED"
        return "ACTIVE" if age <= max(1, settings.knowledge_review_days) else "STALE"

    def to_context(self, item: TravelKnowledge, *, match_reasons: list[str] | None = None) -> dict[str, Any]:
        status = self._record_status(item)
        opening = item.opening_hours
        reservation = item.reservation_notice
        verified_age_days = _age_in_days(item.verified_at)
        return {
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "category_label": label_category(item.category),
            "area": item.area,
            "address": item.address,
            "indoor_outdoor": item.indoor_outdoor,
            "indoor_outdoor_label": label_indoor(item.indoor_outdoor),
            "suitable_crowds": item.suitable_crowds,
            "suitable_crowds_label": label_crowds(item.suitable_crowds),
            "minimum_age": item.minimum_age,
            "maximum_age": item.maximum_age,
            "suggested_duration_minutes": item.suggested_duration_minutes,
            "opening_hours": opening,
            "weather_adaptations": item.weather_adaptations,
            "weather_adaptations_label": label_weather(item.weather_adaptations),
            "reservation_notice": reservation,
            "description": item.description,
            "source_name": item.source_name,
            "source_url": item.source_url,
            "source_updated_at": item.source_updated_at.isoformat() if item.source_updated_at else None,
            "source_checked_at": item.source_checked_at.isoformat() if item.source_checked_at else None,
            "source_reachable": item.source_reachable,
            "verified_fields": item.verified_fields or [],
            "verified_at": item.verified_at.isoformat() if item.verified_at else None,
            "source_age_days": verified_age_days,
            "verification_status": status,
            "bookable": False,
            "knowledge_role": "PUBLIC_REFERENCE",
            "fact_boundary": "仅可用于带来源的路线建议；不是酒店正式权益、库存或可预约资源。",
            "match_reasons": match_reasons or [],
        }

    def listing(self, *, query: str = "", category: str = "", limit: int = 80) -> list[dict[str, Any]]:
        """Full records for the workbench knowledge page.

        The operator view keeps every stored field verbatim (source, opening
        hours, reservation notice) so the hotel can review what the skills are
        allowed to quote, instead of seeing a summarised or rewritten version.
        """

        items = list(
            self.db.scalars(
                select(TravelKnowledge).order_by(TravelKnowledge.category, TravelKnowledge.name)
            ).all()
        )
        needle = " ".join(str(query or "").split()).lower()
        category_needle = str(category or "").strip().upper()
        records: list[dict[str, Any]] = []
        for item in items:
            if category_needle and str(item.category or "").upper() != category_needle:
                continue
            if needle:
                haystack = " ".join(
                    str(getattr(item, field, "") or "")
                    for field in ("name", "category", "area", "address", "description", "opening_hours", "reservation_notice", "source_name")
                ).lower()
                if needle not in haystack:
                    continue
            status = self._record_status(item)
            records.append(
                {
                    "id": item.id,
                    "slug": item.slug,
                    "name": item.name,
                    "category": item.category,
                    "category_label": label_category(item.category),
                    "area": item.area,
                    "address": item.address,
                    "indoor_outdoor": item.indoor_outdoor,
                    "indoor_outdoor_label": label_indoor(item.indoor_outdoor),
                    "suitable_crowds": item.suitable_crowds,
                    "suitable_crowds_label": label_crowds(item.suitable_crowds),
                    "minimum_age": item.minimum_age,
                    "maximum_age": item.maximum_age,
                    "suggested_duration_minutes": item.suggested_duration_minutes,
                    "opening_hours": item.opening_hours,
                    "weather_adaptations": item.weather_adaptations,
                    "weather_adaptations_label": label_weather(item.weather_adaptations),
                    "reservation_notice": item.reservation_notice,
                    "description": item.description,
                    "source_name": item.source_name,
                    "source_url": item.source_url,
                    "verified_at": item.verified_at.isoformat() if item.verified_at else None,
                    "verified_by_user_id": item.verified_by_user_id,
                    "verification_note": item.verification_note,
                    "verified_fields": item.verified_fields or [],
                    "source_checked_at": item.source_checked_at.isoformat() if item.source_checked_at else None,
                    "source_reachable": item.source_reachable,
                    "source_updated_at": item.source_updated_at.isoformat() if item.source_updated_at else None,
                    "source_age_days": _age_in_days(item.verified_at),
                    "review_window_days": max(1, settings.knowledge_review_days),
                    "status": status,
                    "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                }
            )
        return records[: max(1, min(int(limit), 200))]

    def categories(self) -> list[dict[str, str]]:
        """Distinct categories with Chinese labels, so the workbench filter is
        never shown as English enum codes."""

        codes = sorted({str(item) for item in self.db.scalars(select(TravelKnowledge.category).distinct()).all() if item})
        return [{"value": code, "label": label_category(code)} for code in codes]

    def total(self) -> int:
        """Number of curated records, so the workbench shows the real count."""

        return int(self.db.scalar(select(func.count()).select_from(TravelKnowledge)) or 0)

    def refresh_sources(self, *, city: str = "杭州", limit: int | None = None) -> dict[str, Any]:
        """Re-check every stored source link and stamp the records that answer.

        Venue pages are the only authority we hold, so the "更新" action
        verifies reachability and refreshes the review timestamp instead of
        inventing new facts.  Records whose source cannot be reached keep their
        previous verification time and are reported back to the operator.
        """

        import httpx

        now = _utc_now()
        statement = select(TravelKnowledge).where(TravelKnowledge.status == "ACTIVE").order_by(TravelKnowledge.name)
        items = list(self.db.scalars(statement).all())
        if city:
            items = [item for item in items if not item.area or city in str(item.area) or city in str(item.address or "")]
        if limit:
            items = items[:limit]
        checked = reachable_count = 0
        failed: list[dict[str, str]] = []
        for item in items:
            url = str(item.source_url or "").strip()
            checked += 1
            if not url:
                item.source_checked_at = now
                item.source_reachable = False
                failed.append({"name": item.name, "reason": "未配置来源链接"})
                continue
            try:
                response = httpx.get(url, timeout=6, follow_redirects=True)
                reachable = response.status_code < 400
            except Exception:  # noqa: BLE001 - network failures are reported, not raised
                reachable = False
            item.source_checked_at = now
            item.source_reachable = reachable
            if reachable:
                reachable_count += 1
            else:
                failed.append({"name": item.name, "reason": "来源页暂时无法访问"})
        self.db.flush()
        return {
            "checked": checked,
            "reachable_count": reachable_count,
            "facts_reverified": 0,
            "failed": failed[:10],
            "failed_count": len(failed),
            "checked_at": now.isoformat(),
        }

    def review_item(self, item_id: int, *, reviewer_id: int, reviewed_fields: list[str], note: str) -> dict[str, Any]:
        required = {"name", "category", "area", "address", "indoor_outdoor", "suitable_crowds", "minimum_age", "maximum_age", "suggested_duration_minutes", "opening_hours", "weather_adaptations", "reservation_notice", "description", "source_name", "source_url"}
        if set(reviewed_fields) != required:
            raise ValueError("必须逐项核对全部知识字段")
        clean_note = " ".join(str(note or "").split())
        if len(clean_note) < 8:
            raise ValueError("核验说明至少需要 8 个字符")
        item = self.db.get(TravelKnowledge, item_id)
        if item is None:
            raise LookupError("知识记录不存在")
        if not str(item.source_url or "").strip():
            raise ValueError("缺少可追溯的来源链接，不能记录事实核验")
        now = _utc_now()
        item.verified_at = now
        item.verified_by_user_id = reviewer_id
        item.verification_note = clean_note[:1000]
        item.verified_fields = sorted(required)
        item.verification_status = "ACTIVE"
        self.db.flush()
        return self.to_context(item)

    def search(self, query: str = "", *, target_crowd: str = "", weather: str = "", limit: int = 8) -> list[dict[str, Any]]:
        items = list(
            self.db.scalars(
                select(TravelKnowledge)
                .where(TravelKnowledge.status == "ACTIVE")
                .order_by(TravelKnowledge.name)
            ).all()
        )
        normalized_query = query.lower().strip()
        words = [word.lower() for word in query.replace("，", " ").replace("、", " ").split() if word.strip()]

        def item_haystack(item: TravelKnowledge) -> str:
            return (
                f"{item.name} {item.category} {item.area} {item.address} "
                f"{item.description} {item.suitable_crowds} {item.indoor_outdoor}"
            ).lower()

        def reasons(item: TravelKnowledge) -> list[str]:
            haystack = item_haystack(item)
            result: list[str] = []
            if item.name.lower() in normalized_query:
                result.append("名称匹配")
            for word in words:
                if word and word in haystack:
                    result.append(f"关键词：{word}")
            uppercase = haystack.upper()
            for phrase, tags in _QUERY_ALIASES.items():
                if phrase in normalized_query and any(tag in uppercase for tag in tags):
                    result.append(f"意图：{phrase}")
            if target_crowd and (target_crowd in item.suitable_crowds or "ALL" in item.suitable_crowds):
                result.append("客群适配")
            if weather and weather in item.weather_adaptations:
                result.append("天气适配")
            if item.indoor_outdoor == "INDOOR" and weather == "RAIN":
                result.append("雨天室内")
            return list(dict.fromkeys(result))

        def score(item: TravelKnowledge) -> int:
            haystack = item_haystack(item)
            result = sum(5 for word in words if word in haystack)
            uppercase = haystack.upper()
            for phrase, tags in _QUERY_ALIASES.items():
                if phrase in normalized_query and any(tag in uppercase for tag in tags):
                    result += 9
            if item.name.lower() in normalized_query:
                result += 12
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
        return [self.to_context(item, match_reasons=reasons(item)) for item in ranked[: max(1, min(limit, 20))]]
