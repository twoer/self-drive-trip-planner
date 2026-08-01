#!/usr/bin/env python3
"""Parse compact Chinese self-drive itinerary text into day/leg blocks."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


DAY_PREFIX_RE = re.compile(r"^(?:(?:D|DAY)\s*(\d+)|第\s*([0-9一二两俩三四五六七八九十〇零]+)\s*天)(.*)$", re.IGNORECASE)
ROUTE_CONNECTOR_RE = re.compile(r"\s*(?:->|→|到达|前往|去往|返回|回到|回|到|至)\s*|\s+[-—–]\s+")
CHINESE_DAY_NUMBER_VALUES = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "俩": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def parse_day_number(value: str) -> int | None:
    text = value.strip()
    if text.isdigit():
        return int(text)
    if text in CHINESE_DAY_NUMBER_VALUES:
        return CHINESE_DAY_NUMBER_VALUES[text]
    if text.startswith("十") and len(text) == 2:
        return 10 + CHINESE_DAY_NUMBER_VALUES.get(text[1], 0)
    if text.endswith("十") and len(text) == 2:
        return CHINESE_DAY_NUMBER_VALUES.get(text[0], 0) * 10
    if "十" in text and len(text) == 3:
        return CHINESE_DAY_NUMBER_VALUES.get(text[0], 0) * 10 + CHINESE_DAY_NUMBER_VALUES.get(text[2], 0)
    return None


def has_route_connector(value: str) -> bool:
    return bool(ROUTE_CONNECTOR_RE.search(value))


def normalize_route_connectors(value: str) -> str:
    return ROUTE_CONNECTOR_RE.sub(" 到 ", value)


def split_day_prefix(line: str) -> tuple[int, str] | None:
    normalized_line = unicodedata.normalize("NFKC", line.strip())
    match = DAY_PREFIX_RE.match(normalized_line)
    if not match:
        return None
    day_number = parse_day_number(match.group(1) or match.group(2))
    if day_number is None:
        return None
    raw_remainder = match.group(3)
    if not raw_remainder:
        return day_number, ""
    has_separator = bool(re.match(r"^\s*(?:[：:、，,.\-—]\s*|\s+)", raw_remainder))
    remainder = re.sub(r"^\s*(?:[：:、，,.\-—]\s*|\s+)", "", raw_remainder).strip()
    if has_separator or has_route_connector(remainder):
        return day_number, remainder
    return None


def explicit_day_numbers(text: str) -> set[int]:
    numbers = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        day_prefix = split_day_prefix(line)
        if day_prefix:
            numbers.add(day_prefix[0])
    return numbers


def next_day_label(days: list[dict[str, Any]], reserved_numbers: set[int] | None = None) -> str:
    reserved = reserved_numbers or set()
    used_numbers = set()
    for day in days:
        match = re.match(r"^D(\d+)$", str(day.get("day", "")))
        if match:
            used_numbers.add(int(match.group(1)))
    number = 1
    while number in used_numbers or number in reserved:
        number += 1
    return f"D{number}"


def parse_itinerary(text: str) -> list[dict[str, Any]]:
    days: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    reserved_numbers = explicit_day_numbers(text)
    explicit_numbers_seen: set[int] = set()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        day_prefix = split_day_prefix(line)
        if day_prefix:
            day_number, remainder = day_prefix
            if day_number < 1:
                raise ValueError(f"Invalid day label: {line}. Day numbers must start at 1.")
            if day_number in explicit_numbers_seen:
                raise ValueError(f"Duplicate day label: D{day_number}. Each explicit day label must be unique.")
            explicit_numbers_seen.add(day_number)
            carried_notes = []
            if current and current.get("_implicit") and not current["legs"]:
                carried_notes = list(current.get("notes") or [])
                if days and days[-1] is current:
                    days.pop()
            current = {"day": f"D{day_number}", "legs": [], "notes": carried_notes}
            days.append(current)
            if not remainder:
                continue
            line = remainder

        if current is None:
            current = {"day": next_day_label(days, reserved_numbers), "legs": [], "notes": [], "_implicit": True}
            days.append(current)

        normalized = normalize_route_connectors(line)
        if " 到 " not in normalized:
            current.setdefault("notes", []).append(line)
            continue

        stops = [part.strip() for part in normalized.split(" 到 ") if part.strip()]
        for origin, destination in zip(stops, stops[1:]):
            current["legs"].append({"from": origin, "to": destination})

    result = []
    for day in days:
        day.pop("_implicit", None)
        if day["legs"] or day.get("notes"):
            result.append(day)
    return result
