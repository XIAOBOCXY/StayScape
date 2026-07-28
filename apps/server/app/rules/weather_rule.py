from ..core.exceptions import AppError
from .availability_rule import tokens


def is_weather_supported(weather_tags: str | None, weather: str) -> bool:
    weather_key = (weather or "SUNNY").upper()
    tags = tokens(weather_tags)
    return weather_key in tags or "ALL" in tags


def validate_weather(weather_tags: str | None, weather: str, resource_name: str) -> None:
    if not is_weather_supported(weather_tags, weather):
        raise AppError(
            "WEATHER_NOT_SUPPORTED",
            f"{resource_name}不支持当前天气条件",
            field="weather",
            retryable=True,
            suggestion="选择室内或支持当前天气的替代资源",
        )

