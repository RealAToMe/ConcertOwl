"""票牛移动站公开搜索 API。

用于按歌手发现活动；价格采集仍由 collectors.piaoniu 读取活动详情与票档。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import requests

API_ORIGIN = "https://api.piaoniu.com"
WEB_ORIGIN = "https://x.piaoniu.com"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Origin": "https://m.piaoniu.com",
    "Referer": "https://m.piaoniu.com/",
}


@dataclass
class PiaoniuActivity:
    activity_id: str
    artist: str
    name: str = ""
    city: str = ""
    start_date: str = ""
    end_date: str = ""
    time_range: str = ""
    status: str = ""
    min_price: Optional[float] = None
    proxy_buy: bool = False

    @property
    def web_url(self) -> str:
        return f"{WEB_ORIGIN}/activity/{self.activity_id}"


def _date_from_ms(value) -> str:
    try:
        dt = datetime.fromtimestamp(
            float(value) / 1000,
            tz=timezone(timedelta(hours=8)),
        )
        return dt.date().isoformat()
    except (TypeError, ValueError, OSError):
        return ""


def _to_float(value) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class PiaoniuClient:
    def __init__(self, min_interval: float = 0.8, timeout: float = 20.0):
        self.min_interval = min_interval
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)
        self._last = 0.0

    def _throttle(self) -> None:
        wait = self.min_interval - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()

    def search_artist(self, artist: str) -> List[PiaoniuActivity]:
        """返回该歌手仍在观察窗口内的票牛活动。"""
        self._throttle()
        payload = {
            "keyword": artist,
            "pageIndex": 1,
            "pageSize": 8,
            "needRelatedTours": True,
            "needRelatedActivities": True,
            "needActivityPrice": True,
            "needActivityTime": True,
            "filterExpiredActivityDays": 15,
        }
        try:
            resp = self._session.post(
                API_ORIGIN + "/v1/actorAggregation/query",
                json=payload,
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return []
            resp.encoding = "utf-8"
            body = resp.json()
        except (requests.RequestException, ValueError):
            return []

        out: List[PiaoniuActivity] = []
        seen = set()
        for actor in body.get("data") or []:
            actor_name = str(actor.get("name") or "")
            if actor_name.strip().lower() != artist.strip().lower():
                continue
            for tour in actor.get("tours") or []:
                for raw in tour.get("activities") or []:
                    activity_id = str(
                        raw.get("activityId") or raw.get("id") or ""
                    ).strip()
                    if not activity_id or activity_id in seen:
                        continue
                    seen.add(activity_id)
                    name = str(raw.get("name") or "")
                    tag = str(raw.get("activityInTourTagType") or "")
                    proxy_buy = (
                        tag.upper() == "PROXY_BUY"
                        or any(
                            marker in name
                            for marker in ("代拍费", "补款", "预定金", "订金")
                        )
                    )
                    out.append(
                        PiaoniuActivity(
                            activity_id=activity_id,
                            artist=actor_name,
                            name=name,
                            city=str(raw.get("cityName") or ""),
                            start_date=_date_from_ms(raw.get("startTime")),
                            end_date=_date_from_ms(raw.get("endTime")),
                            time_range=str(raw.get("timeRange") or ""),
                            status=str(raw.get("status") or ""),
                            min_price=_to_float(raw.get("lowPrice")),
                            proxy_buy=proxy_buy,
                        )
                    )
        return out
