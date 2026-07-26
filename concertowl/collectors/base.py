"""采集器基类：统一的限速 HTTP 会话与容错。

设计原则：
- 单个源失败绝不影响其它源（collect 内部吞掉异常并返回空 + 记录 note）。
- 严格低频、带 UA、随机抖动，个人自用，尊重目标站点。
"""
from __future__ import annotations

import random
import time
from typing import List, Optional

import requests

from ..models import PriceSnapshot, WatchEvent, now_local_iso, days_between

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class Collector:
    source: str = "base"
    #: 该采集器负责哪些 Watchlist.secondary_url / official_url 前缀
    url_hints: tuple = ()

    def __init__(self, min_interval: float = 2.0, timeout: float = 15.0):
        self.min_interval = min_interval
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)
        self._last_request = 0.0

    # ---- HTTP 帮助 ----
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

    # ---- 子类实现 ----
    def handles(self, event: WatchEvent) -> bool:
        """该采集器是否负责这场演出（默认看 URL 是否匹配 hint）。"""
        url = self._target_url(event) or ""
        return any(h in url for h in self.url_hints)

    def _target_url(self, event: WatchEvent) -> Optional[str]:
        raise NotImplementedError

    def fetch(self, event: WatchEvent) -> List[PriceSnapshot]:
        """真正解析目标页/接口，返回快照。子类实现。"""
        raise NotImplementedError

    # ---- 对外统一入口，带容错 ----
    def collect(self, event: WatchEvent) -> List[PriceSnapshot]:
        try:
            snaps = self.fetch(event)
        except Exception as exc:  # 绝不让单点异常炸掉整轮
            return [self._error_snapshot(event, f"{type(exc).__name__}: {exc}")]
        return snaps

    # ---- 快照构造帮助 ----
    def _base_snapshot(self, event: WatchEvent, **kw) -> PriceSnapshot:
        return PriceSnapshot(
            ts=now_local_iso(),
            event_id=event.event_id,
            source=self.source,
            days_to_show=days_between(event.show_datetime),
            **kw,
        )

    def _error_snapshot(self, event: WatchEvent, note: str) -> PriceSnapshot:
        return self._base_snapshot(event, official_status="未知", raw_note=f"ERROR {note}")

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

    def _premium_ratio(self, event: WatchEvent, listed_min: Optional[float]) -> Optional[float]:
        faces = self.face_price_list(event)
        if listed_min is None or not faces:
            return None
        base = min(faces)
        if base <= 0:
            return None
        return round(listed_min / base, 3)
