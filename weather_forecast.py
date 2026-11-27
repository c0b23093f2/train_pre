"""東京の天気予報（Open-Meteo）を取得する。予測モデルに渡す「1日の降水量」と「1日の平均風速」を作る。

API キーは不要。昨日の分も一緒に取る（前日の降水量として使うため）。
"""
from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from datetime import date

import certifi

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TOKYO = (35.692, 139.750)          # 気象庁（東京）の観測地点のおおよその位置
FORECAST_DAYS = 8                  # 今日を含めて8日分（＝7日先まで）


class ForecastError(Exception):
    """天気予報を取得できなかった・形が想定と違ったときのエラー"""


def download_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "university-class-project (data analysis practice)"})
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, timeout=15, context=context) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_forecast(payload: dict) -> dict[date, dict]:
    """API の返事 → {日付: {"precip": 降水量の合計(mm), "wind": 平均風速(m/s)}}。値が無い項目は None。"""
    try:
        days = payload["daily"]["time"]
        rain = payload["daily"]["precipitation_sum"]
        hours = payload["hourly"]["time"]
        wind = payload["hourly"]["wind_speed_10m"]
    except (KeyError, TypeError) as error:
        raise ForecastError("予報データに必要な項目がありません。") from error

    wind_by_day: dict[str, list[float]] = {}
    for moment, value in zip(hours, wind):
        if value is not None:
            wind_by_day.setdefault(str(moment)[:10], []).append(float(value))   # "2026-11-27T09:00" → 日付

    result = {}
    for day, value in zip(days, rain):
        values = wind_by_day.get(day, [])
        result[date.fromisoformat(day)] = {
            "precip": None if value is None else float(value),
            "wind": round(sum(values) / len(values), 1) if values else None,   # 1時間ごとの風速を平均する
        }
    if not result:
        raise ForecastError("予報データが空です。")
    return result


def fetch_tokyo_forecast() -> dict[date, dict]:
    """東京の予報（昨日〜7日先）を取得する。失敗したら ForecastError。"""
    query = urllib.parse.urlencode({
        "latitude": TOKYO[0], "longitude": TOKYO[1],
        "daily": "precipitation_sum", "hourly": "wind_speed_10m",
        "wind_speed_unit": "ms",                 # 気象庁と同じ m/s でもらう
        "timezone": "Asia/Tokyo", "past_days": 1, "forecast_days": FORECAST_DAYS,
    })
    try:
        payload = download_json(f"{FORECAST_URL}?{query}")
    except Exception as error:
        raise ForecastError(f"天気予報 API に接続できませんでした（{type(error).__name__}）。") from error
    return parse_forecast(payload)
