"""Cityline（购票通，cityline.com.hk）港澳官方场次 / 售罄状态采集器。

Cityline 是一手官方售票平台，主要用于拿官方票价档位与「是否售罄」。
以事件页 HTML 解析为主（价格档 + 状态关键词）。
"""
from __future__ import annotations

from typing import List, Optional

from bs4 import BeautifulSoup

from ..models import PriceSnapshot, WatchEvent
from .base import Collector
from . import _htmlutil as H


class CitylineCollector(Collector):
    source = "cityline"
    url_hints = ("cityline.com", "cityline.com.hk")

    def _target_url(self, event: WatchEvent) -> Optional[str]:
        # 港澳官方链接放在 official_url；仅当指向 cityline 才处理
        url = event.official_url or ""
        return url if any(h in url for h in self.url_hints) else None

    def fetch(self, event: WatchEvent) -> List[PriceSnapshot]:
        url = self._target_url(event)
        if not url:
            return []
        resp = self.get(url)
        if resp is None:
            return [self._error_snapshot(event, "fetch failed / blocked")]

        soup = BeautifulSoup(resp.text, "lxml")
        text = soup.get_text(" ", strip=True)

        prices = H.extract_prices(text)
        low = min(prices) if prices else None
        status = H.guess_status(text)
        return [
            self._base_snapshot(
                event,
                tier="overall_min",
                face_price=None,
                listed_min=low,
                listed_median=H.median(prices),
                premium_ratio=self._premium_ratio(event, low),
                official_status=status,
                raw_note="cityline-html" if low else "no-price-parsed",
            )
        ]
