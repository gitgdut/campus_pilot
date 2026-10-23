"""Open-Meteo 天气服务，包含输入校验和可注入 HTTP 层。"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

JsonGetter = Callable[[str, dict[str, Any]], dict[str, Any]]

WEATHER_DESCRIPTIONS = {
    0: "晴",
    1: "大致晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "强毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "小阵雨",
    81: "阵雨",
    82: "强阵雨",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴大冰雹",
}


def _default_get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    request = Request(
        f"{url}?{urlencode(params)}",
        headers={"User-Agent": "CampusPilot/0.3"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            return json.load(response)
    except Exception as exc:
        raise RuntimeError(f"天气服务请求失败：{exc}") from exc


class WeatherService:
    """查询地点坐标，并获取 Open-Meteo 逐日预报。"""

    def __init__(self, get_json: JsonGetter | None = None) -> None:
        self.get_json = get_json or _default_get_json

    def get_forecast(
        self,
        city: str,
        start_date: str,
        days: int = 3,
    ) -> dict[str, Any]:
        city = city.strip()
        if not city:
            raise ValueError("城市名称不能为空")
        try:
            first_day = date.fromisoformat(start_date)
        except ValueError as exc:
            raise ValueError("start_date 必须是 YYYY-MM-DD 格式") from exc
        if not 1 <= days <= 7:
            raise ValueError("天气查询天数必须在 1 到 7 天之间")
        last_day = first_day + timedelta(days=days - 1)

        location_data = self.get_json(
            "https://geocoding-api.open-meteo.com/v1/search",
            {"name": city, "count": 1, "language": "zh", "format": "json"},
        )
        results = location_data.get("results") or []
        if not results:
            raise LookupError(f"没有找到城市：{city}")
        location = results[0]

        forecast_data = self.get_json(
            "https://api.open-meteo.com/v1/forecast",
            {
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "daily": (
                    "weather_code,temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max"
                ),
                "timezone": "auto",
                "start_date": first_day.isoformat(),
                "end_date": last_day.isoformat(),
            },
        )
        daily = forecast_data.get("daily") or {}
        dates = daily.get("time") or []
        forecasts = []
        for index, forecast_date in enumerate(dates):
            code = daily["weather_code"][index]
            forecasts.append(
                {
                    "date": forecast_date,
                    "weather_code": code,
                    "weather": WEATHER_DESCRIPTIONS.get(code, f"未知天气代码 {code}"),
                    "temperature_max_c": daily["temperature_2m_max"][index],
                    "temperature_min_c": daily["temperature_2m_min"][index],
                    "precipitation_probability_percent": daily[
                        "precipitation_probability_max"
                    ][index],
                }
            )
        if not forecasts:
            raise RuntimeError("天气服务没有返回逐日预报")

        display_name = ", ".join(
            str(value)
            for value in (location.get("name"), location.get("admin1"), location.get("country"))
            if value
        )
        return {
            "location": display_name,
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "timezone": forecast_data.get("timezone"),
            "forecasts": forecasts,
            "source": "Open-Meteo",
        }
