"""Sourced, cached weather context for hotel product planning.

The product model still stores a compact compatibility tag (RAIN/SUNNY/CLOUDY),
but that tag is resolved here from a provider response.  If a date is outside a
provider horizon or a provider fails, callers receive an explicit
``VERIFY_REQUIRED`` result instead of a guessed forecast.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import WeatherSnapshot


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
# The contest demo is Hangzhou-first.  Unknown cities intentionally do not use a
# fuzzy geocoder: an unverified location is safer than a wrong forecast.
CITY_COORDINATES: dict[str, tuple[float, float]] = {
    "杭州": (30.2741, 120.1551),
    "杭州市": (30.2741, 120.1551),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _scenario(code: int | None, precipitation_probability: int | None) -> str:
    if (precipitation_probability or 0) >= 45 or (code is not None and code >= 50):
        return "RAIN"
    if code in {0, 1}:
        return "SUNNY"
    return "CLOUDY"


class WeatherService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _serialize(snapshot: WeatherSnapshot, *, note: str = "") -> dict[str, Any]:
        minimum = float(snapshot.temperature_min) if snapshot.temperature_min is not None else None
        maximum = float(snapshot.temperature_max) if snapshot.temperature_max is not None else None
        return {
            "city": snapshot.city,
            "target_date": snapshot.target_date.isoformat(),
            "scenario": snapshot.scenario,
            "temperature_min": minimum,
            "temperature_max": maximum,
            "precipitation_probability": snapshot.precipitation_probability,
            "weather_code": snapshot.weather_code,
            "advisory": note or snapshot.advisory,
            "source_name": snapshot.source_name,
            "source_url": snapshot.source_url,
            "fetched_at": snapshot.fetched_at.isoformat(),
            "expires_at": snapshot.expires_at.isoformat() if snapshot.expires_at else None,
            "verification_status": snapshot.verification_status,
            "usable": snapshot.verification_status == "ACTIVE",
        }

    @staticmethod
    def _unverified(city: str, target_date: date, advisory: str) -> dict[str, Any]:
        return {
            "city": city,
            "target_date": target_date.isoformat(),
            "scenario": "CLOUDY",
            "temperature_min": None,
            "temperature_max": None,
            "precipitation_probability": None,
            "weather_code": None,
            "advisory": advisory,
            "source_name": "天气信息待确认",
            "source_url": "",
            "fetched_at": None,
            "expires_at": None,
            "verification_status": "VERIFY_REQUIRED",
            "usable": False,
        }

    def get_forecast(self, city: str, target_date: date, *, force_refresh: bool = False) -> dict[str, Any]:
        normalized_city = city.strip() or "杭州"
        now = _utc_now()
        cached = self.db.scalar(
            select(WeatherSnapshot).where(
                WeatherSnapshot.city == normalized_city,
                WeatherSnapshot.target_date == target_date,
            )
        )
        if cached and not force_refresh and cached.expires_at and cached.expires_at > now:
            return self._serialize(cached)

        # Offline demo/test runs must never create a hidden external dependency.
        # Live OpenClaw deployments still retrieve the forecast below.
        if settings.mode.lower() != "live" and settings.agent_provider.lower() == "mock":
            return self._unverified(normalized_city, target_date, "演示模式未调用外部天气服务；天气信息需确认。")

        coordinates = CITY_COORDINATES.get(normalized_city)
        horizon = max(1, settings.weather_forecast_days)
        if not coordinates:
            return self._serialize(cached, note="当前城市尚未配置可信天气坐标，天气信息需确认。") if cached else self._unverified(normalized_city, target_date, "当前城市尚未配置可信天气坐标，天气信息需确认。")
        if target_date < date.today() or target_date > date.today() + timedelta(days=horizon):
            note = f"目标日期不在当前 {horizon} 天预报范围内，天气信息需确认。"
            return self._serialize(cached, note=note) if cached else self._unverified(normalized_city, target_date, note)
        if not settings.weather_enabled or settings.weather_provider.lower() != "open_meteo":
            note = "天气服务未启用，生成时不会把天气当作已确认事实。"
            return self._serialize(cached, note=note) if cached else self._unverified(normalized_city, target_date, note)

        try:
            response = httpx.get(
                OPEN_METEO_URL,
                params={
                    "latitude": coordinates[0],
                    "longitude": coordinates[1],
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "timezone": "Asia/Shanghai",
                    "forecast_days": horizon,
                },
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            daily = payload.get("daily") or {}
            dates = list(daily.get("time") or [])
            index = dates.index(target_date.isoformat())
            weather_code = int((daily.get("weather_code") or [])[index])
            maximum = Decimal(str((daily.get("temperature_2m_max") or [])[index]))
            minimum = Decimal(str((daily.get("temperature_2m_min") or [])[index]))
            probability_value = (daily.get("precipitation_probability_max") or [None])[index]
            probability = int(probability_value) if probability_value is not None else None
        except (httpx.HTTPError, ValueError, IndexError, TypeError):
            note = "天气服务暂时未返回可核验预报，生成时将保留可替换安排。"
            return self._serialize(cached, note=note) if cached else self._unverified(normalized_city, target_date, note)

        scenario = _scenario(weather_code, probability)
        advisory = (
            "降雨概率较高，优先安排室内或可替换体验。"
            if scenario == "RAIN"
            else "天气条件适合安排已核验资源；出行前仍请以最新预报为准。"
        )
        expires_at = now + timedelta(hours=max(1, settings.weather_cache_hours))
        if cached is None:
            cached = WeatherSnapshot(
                city=normalized_city,
                target_date=target_date,
                scenario=scenario,
                temperature_min=minimum,
                temperature_max=maximum,
                precipitation_probability=probability,
                weather_code=weather_code,
                advisory=advisory,
                source_name="Open-Meteo Forecast API",
                source_url=OPEN_METEO_URL,
                fetched_at=now,
                expires_at=expires_at,
                verification_status="ACTIVE",
                raw_payload={"daily": daily},
            )
            self.db.add(cached)
        else:
            cached.scenario = scenario
            cached.temperature_min = minimum
            cached.temperature_max = maximum
            cached.precipitation_probability = probability
            cached.weather_code = weather_code
            cached.advisory = advisory
            cached.source_name = "Open-Meteo Forecast API"
            cached.source_url = OPEN_METEO_URL
            cached.fetched_at = now
            cached.expires_at = expires_at
            cached.verification_status = "ACTIVE"
            cached.raw_payload = {"daily": daily}
        self.db.flush()
        return self._serialize(cached)
