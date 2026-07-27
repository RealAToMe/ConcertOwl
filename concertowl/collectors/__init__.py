"""价格采集器。每个平台一个适配器，统一输出 PriceSnapshot 列表。"""
from __future__ import annotations

from typing import List

from .base import Collector
from .damai import DamaiCollector
from .moretickets import MoreTicketsCollector
from .cityline import CitylineCollector
from .piaoniu import PiaoniuCollector


def all_collectors() -> List[Collector]:
    return [
        DamaiCollector(),
        MoreTicketsCollector(),
        PiaoniuCollector(),
        CitylineCollector(),
    ]


def collectors_by_name() -> dict:
    return {c.source: c for c in all_collectors()}
