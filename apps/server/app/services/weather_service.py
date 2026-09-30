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


def _is_fresh(snapshot: WeatherSnapshot, now: datetime | None = None) -> bool:
    expires_at = snapshot.expires_at
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > (now or _utc_now())


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
            "usable": snapshot.verification_status == "ACTIVE" and _is_fresh(snapshot),
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
        if cached and not force_refresh and _is_fresh(cached, now):
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
        # Report the actual forecast instead of a generic disclaimer.
        scenario_label = {"RAIN": "有降雨", "SUNNY": "晴天", "CLOUDY": "多云"}[scenario]
        temperature_text = f"{float(minimum):.0f}–{float(maximum):.0f}℃"
        rain_text = f"，降雨概率 {probability}%" if probability is not None else ""
        packing = {
            "RAIN": "建议带伞，优先安排室内项目。",
            "SUNNY": "适合户外安排，注意防晒和补水。",
            "CLOUDY": "适合户外安排，早晚温差略大。",
        }[scenario]
        advisory = f"{scenario_label}，气温 {temperature_text}{rain_text}。{packing}"
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

    def get_forecast_range(self, city: str, start_date: date, *, days: int = 15, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Return a date-by-date forecast window using at most one provider call."""

        normalized_city = city.strip() or "杭州"
        count = max(1, min(16, int(days)))
        target_dates = [start_date + timedelta(days=offset) for offset in range(count)]
        now = _utc_now()
        cached_rows = list(
            self.db.scalars(
                select(WeatherSnapshot).where(
                    WeatherSnapshot.city == normalized_city,
                    WeatherSnapshot.target_date >= target_dates[0],
                    WeatherSnapshot.target_date <= target_dates[-1],
                )
            ).all()
        )
        cached_by_date = {row.target_date: row for row in cached_rows}
        fresh_dates = {
            day for day, row in cached_by_date.items()
            if not force_refresh and _is_fresh(row, now)
        }
        needs_provider = any(day not in fresh_dates for day in target_dates)
        payload: dict[str, Any] = {}
        coordinates = CITY_COORDINATES.get(normalized_city)
        horizon = max(1, min(16, int(settings.weather_forecast_days)))

        if needs_provider and coordinates and settings.weather_enabled and settings.weather_provider.lower() == "open_meteo" and not (settings.mode.lower() != "live" and settings.agent_provider.lower() == "mock"):
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
                payload = response.json().get("daily") or {}
            except (httpx.HTTPError, ValueError, TypeError):
                payload = {}

        results: list[dict[str, Any]] = []
        dates = list(payload.get("time") or [])
        expires_at = now + timedelta(hours=max(1, settings.weather_cache_hours))
        for target in target_dates:
            cached = cached_by_date.get(target)
            if target in fresh_dates:
                results.append(self._serialize(cached))
                continue
            outside_provider = target < date.today() or target > date.today() + timedelta(days=horizon - 1)
            if not coordinates:
                note = "当前城市尚未配置可信天气坐标，天气信息需确认。"
            elif outside_provider:
                note = f"目标日期超出当前 {horizon} 天预报范围，天气信息需确认。"
            elif not settings.weather_enabled or settings.weather_provider.lower() != "open_meteo":
                note = "天气服务未启用，天气信息需确认。"
            elif not payload:
                note = "天气服务暂时未返回逐日预报，生成时保留可替换安排。"
            else:
                note = "该日期暂无可核验预报，天气信息需确认。"

            try:
                index = dates.index(target.isoformat())
                code_value = (payload.get("weather_code") or [])[index]
                weather_code = int(code_value) if code_value is not None else None
                max_value = (payload.get("temperature_2m_max") or [])[index]
                min_value = (payload.get("temperature_2m_min") or [])[index]
                maximum = Decimal(str(max_value)) if max_value is not None else None
                minimum = Decimal(str(min_value)) if min_value is not None else None
                probability_values = payload.get("precipitation_probability_max") or []
                probability_value = probability_values[index] if index < len(probability_values) else None
                probability = int(probability_value) if probability_value is not None else None
                if weather_code is None and minimum is None and maximum is None and probability is None:
                    raise ValueError("empty daily forecast")
            except (ValueError, IndexError, TypeError):
                results.append(self._serialize(cached, note=note) if cached else self._unverified(normalized_city, target, note))
                continue

            scenario = _scenario(weather_code, probability)
            scenario_label = {"RAIN": "有降雨", "SUNNY": "晴天", "CLOUDY": "多云"}[scenario]
            temperature_text = f"{float(minimum):.0f}–{float(maximum):.0f}℃" if minimum is not None and maximum is not None else "气温待核验"
            rain_text = f"，降雨概率 {probability}%" if probability is not None else ""
            packing = {"RAIN": "优先安排室内项目。", "SUNNY": "适合户外安排，注意防晒和补水。", "CLOUDY": "可结合路线安排室内外项目。"}[scenario]
            advisory = f"{scenario_label}，{temperature_text}{rain_text}。{packing}"
            if cached is None:
                cached = WeatherSnapshot(
                    city=normalized_city,
                    target_date=target,
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
                    raw_payload={"daily": payload},
                )
                self.db.add(cached)
                cached_by_date[target] = cached
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
                cached.raw_payload = {"daily": payload}
            results.append(self._serialize(cached))

        self.db.flush()
        return results
