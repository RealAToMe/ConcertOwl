"""Cityline 港澳官方场次采集器。"""
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
        url = event.official_url or ""
        return url if any(h in url for h in self.url_hints) else None

    def fetch(self, event: WatchEvent) -> List[PriceSnapshot]:
        url = self._target_url(event)
        if not url:
            return []
        resp = self.get(url)
        if resp is None:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        text = soup.get_text(" ", strip=True)
        prices = H.extract_prices(text)
        low = min(prices) if prices else None
        if low is None:
            return []
        return [
            self.observation(
                event,
                observed_price=low,
                face_price=None,
                status=H.guess_status(text),
                currency="HKD",
                note="cityline-html",
            )
        ]
