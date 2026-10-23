from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from campus_pilot.exporter import export_plan_markdown, render_plan_markdown
from campus_pilot.weather import WeatherService


class WeatherServiceTests(unittest.TestCase):
    def test_geocoding_and_forecast_are_normalized(self) -> None:
        calls: list[tuple[str, dict]] = []

        def fake_get(url: str, params: dict):
            calls.append((url, params))
            if "geocoding" in url:
                return {
                    "results": [
                        {
                            "name": "上海",
                            "admin1": "上海市",
                            "country": "中国",
                            "latitude": 31.22,
                            "longitude": 121.46,
                        }
                    ]
                }
            return {
                "timezone": "Asia/Shanghai",
                "daily": {
                    "time": ["2026-10-23"],
                    "weather_code": [61],
                    "temperature_2m_max": [21.5],
                    "temperature_2m_min": [15.0],
                    "precipitation_probability_max": [70],
                },
            }

        result = WeatherService(fake_get).get_forecast("上海", "2026-10-23", 1)
        self.assertEqual(result["forecasts"][0]["weather"], "小雨")
        self.assertEqual(result["forecasts"][0]["temperature_max_c"], 21.5)
        self.assertEqual(len(calls), 2)

    def test_unknown_city_and_invalid_days_are_rejected(self) -> None:
        service = WeatherService(lambda _url, _params: {"results": []})
        with self.assertRaises(LookupError):
            service.get_forecast("不存在的地方", "2026-10-23", 1)
        with self.assertRaisesRegex(ValueError, "1 到 7"):
            service.get_forecast("上海", "2026-10-23", 8)


class MarkdownExporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = {
            "start_date": "2026-10-22",
            "end_date": "2026-10-24",
            "daily_available_minutes": 120,
            "blocks": [
                {
                    "date": "2026-10-22",
                    "task_id": 1,
                    "title": "软件工程作业",
                    "course": "软件工程",
                    "minutes": 60,
                }
            ],
            "unscheduled": [],
            "total_planned_minutes": 60,
        }

    def test_render_and_export_markdown(self) -> None:
        content = render_plan_markdown(self.plan)
        self.assertIn("# CampusPilot 学习计划", content)
        self.assertIn("软件工程作业", content)
        with tempfile.TemporaryDirectory() as temp_dir:
            exported = export_plan_markdown(
                self.plan, temp_dir, "本周 学习计划.md"
            )
            path = Path(exported["path"])
            self.assertEqual(path.parent, Path(temp_dir).resolve())
            self.assertEqual(path.name, "本周-学习计划.md")
            self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_filename_cannot_escape_export_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            exported = export_plan_markdown(
                self.plan, temp_dir, "../../outside.md"
            )
            self.assertEqual(Path(exported["path"]).parent, Path(temp_dir).resolve())
