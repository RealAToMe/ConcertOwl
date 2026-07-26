"""加载 Cities / Artists 白名单，并提供归一化匹配。"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

import yaml

from .models import Artist, City

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")


@lru_cache(maxsize=1)
def load_cities() -> List[City]:
    path = os.path.join(CONFIG_DIR, "cities.yml")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    out: List[City] = []
    for item in data.get("cities", []):
        out.append(
            City(
                name=item["name"],
                region=item.get("region", "CN"),
                band=item.get("band", ""),
                aliases=item.get("aliases", []) or [],
            )
        )
    return out


@lru_cache(maxsize=1)
def load_artists(active_only: bool = False) -> List[Artist]:
    path = os.path.join(CONFIG_DIR, "artists.yml")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    out: List[Artist] = []
    for item in data.get("artists", []):
        a = Artist(
            name=item["name"],
            tier=item.get("tier", "B"),
            active=bool(item.get("active", True)),
            aliases=item.get("aliases", []) or [],
        )
        if active_only and not a.active:
            continue
        out.append(a)
    return out


def active_artists() -> List[Artist]:
    return [a for a in load_artists() if a.active]


def match_city(text: str) -> Optional[City]:
    for c in load_cities():
        if c.matches(text):
            return c
    return None


def match_artist(text: str, active_only: bool = True) -> Optional[Artist]:
    for a in load_artists():
        if active_only and not a.active:
            continue
        if a.matches(text):
            return a
    return None


def in_scope(text: str) -> bool:
    """标题/描述里同时命中白名单城市与在采歌手，才算在范围内。"""
    return match_city(text) is not None and match_artist(text) is not None
