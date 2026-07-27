"""采集器基类：统一限速 HTTP 与观测构造。"""
from __future__ import annotations

import random
import time
from typing import List, Optional

import requests

from ..models import PriceSnapshot, WatchEvent
from ..snapshots import build_observation

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class Collector:
    source: str = "base"
    url_hints: tuple = ()

    def __init__(self, min_interval: float = 2.0, timeout: float = 15.0):
        self.min_interval = min_interval
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)
        self._last_request = 0.0

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request
        wait = self.min_interval - elapsed
        if wait > 0:
            time.sleep(wait + random.uniform(0, 0.8))
        self._last_request = time.time()

    def get(self, url: str, **kwargs) -> Optional[requests.Response]:
        self._throttle()
        try:
            resp = self._session.get(url, timeout=self.timeout, **kwargs)
            if resp.status_code == 200:
                return resp
            return None
        except requests.RequestException:
            return None

    def handles(self, event: WatchEvent) -> bool:
        url = self._target_url(event) or ""
        return any(h in url for h in self.url_hints)

    def _target_url(self, event: WatchEvent) -> Optional[str]:
        raise NotImplementedError

    def fetch(self, event: WatchEvent) -> List[PriceSnapshot]:
        raise NotImplementedError

    def collect(self, event: WatchEvent) -> List[PriceSnapshot]:
        try:
            return self.fetch(event)
        except Exception as exc:
            # 错误不写时序（无价格），只打日志用空列表；需要痕迹时由调用方打印
            print(f"[collect][{self.source}] ERROR {event.event_id}: {type(exc).__name__}: {exc}")
            return []

    def observation(
        self,
        event: WatchEvent,
        *,
        observed_price: Optional[float],
        face_price: Optional[float] = None,
        status: str = "未知",
        currency: str = "",
        note: str = "",
        source: Optional[str] = None,
    ) -> PriceSnapshot:
        return build_observation(
            event,
            observed_price=observed_price,
            face_price=face_price,
            source=source or self.source,
            status=status,
            currency=currency,
            note=note,
        )

    @staticmethod
    def face_price_list(event: WatchEvent) -> List[float]:
        out: List[float] = []
        for part in (event.face_prices or "").replace("，", "/").replace(",", "/").split("/"):
            part = part.strip()
            if not part:
                continue
            try:
                out.append(float(part))
            except ValueError:
                continue
        return out
