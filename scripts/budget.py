"""Budget parsing and calculation helpers for self-drive trip outputs."""

from __future__ import annotations

import argparse
import math
import re
from typing import Any

from itinerary_parser import split_day_prefix


BUDGET_CATEGORY_LABELS = {
    "toll": "过路费",
    "vehicle_energy": "补能",
    "hotel": "住宿",
    "meal": "餐饮",
    "attraction": "景点",
    "misc": "其他",
}
BUDGET_CATEGORY_CHOICES = tuple(BUDGET_CATEGORY_LABELS)
BUDGET_CONTRACT_FIELDS = frozenset(
    {
        "currency",
        "configured",
        "total_cny",
        "category_totals",
        "items",
        "missing_attractions",
        "assumptions",
        "warnings",
    }
)


def money_label(value: float | int | None) -> str:
    if value is None:
        return "待核实"
    return f"¥{int(round(float(value)))}"


def unit_money_label(value: float | int | None) -> str:
    if value is None:
        return "待核实"
    amount = float(value)
    if amount.is_integer():
        return f"¥{int(amount)}"
    return f"¥{amount:.2f}".rstrip("0").rstrip(".")


def compact_number_label(value: float | int, digits: int = 1) -> str:
    number = round(float(value), digits)
    if number.is_integer():
        return str(int(number))
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def parse_named_amount(value: str) -> dict[str, Any]:
    """Parse CLI values like ``小七孔=120`` or ``门票:80``."""
    raw = value.strip()
    if not raw:
        raise argparse.ArgumentTypeError("empty fee item")
    if "=" in raw:
        name, amount = raw.split("=", 1)
    elif ":" in raw:
        name, amount = raw.split(":", 1)
    elif "：" in raw:
        name, amount = raw.split("：", 1)
    else:
        raise argparse.ArgumentTypeError(f"fee item must use NAME=AMOUNT: {value}")
    name = name.strip()
    if not name:
        raise argparse.ArgumentTypeError(f"fee item name is empty: {value}")
    try:
        amount_value = float(amount.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"fee item amount must be numeric: {value}") from exc
    if not math.isfinite(amount_value):
        raise argparse.ArgumentTypeError(f"fee item amount must be finite: {value}")
    if amount_value < 0:
        raise argparse.ArgumentTypeError(f"fee item amount cannot be negative: {value}")
    return {"name": name, "amount_cny": amount_value}


def parse_non_negative_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected a numeric value: {value}") from exc
    if not math.isfinite(number):
        raise argparse.ArgumentTypeError(f"value must be finite: {value}")
    if number < 0:
        raise argparse.ArgumentTypeError(f"value cannot be negative: {value}")
    return number


def parse_positive_float(value: str) -> float:
    number = parse_non_negative_float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError(f"value must be greater than 0: {value}")
    return number


def parse_non_negative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected an integer value: {value}") from exc
    if number < 0:
        raise argparse.ArgumentTypeError(f"value cannot be negative: {value}")
    return number


CHINESE_NUMBER_VALUES = {
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


def parse_small_count(value: str) -> int | None:
    text = value.strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text in CHINESE_NUMBER_VALUES:
        return CHINESE_NUMBER_VALUES[text]
    if text.startswith("十") and len(text) == 2:
        return 10 + CHINESE_NUMBER_VALUES.get(text[1], 0)
    if text.endswith("十") and len(text) == 2:
        return CHINESE_NUMBER_VALUES.get(text[0], 0) * 10
    if "十" in text and len(text) == 3:
        return CHINESE_NUMBER_VALUES.get(text[0], 0) * 10 + CHINESE_NUMBER_VALUES.get(text[2], 0)
    return None


def looks_like_day_line(line: str) -> bool:
    return split_day_prefix(line) is not None


def split_budget_section(text: str) -> tuple[str, str]:
    """Split itinerary text from leading or trailing natural-language budget text."""
    lines = text.splitlines()
    headings = ("费用预算", "预算", "费用", "费用说明", "预算说明")

    def is_budget_heading(value: str) -> bool:
        stripped = value.strip()
        line = stripped.rstrip("：:")
        return line in headings or any(stripped.startswith(f"{heading}{sep}") for heading in headings for sep in ("：", ":"))

    for index, raw_line in enumerate(lines):
        if is_budget_heading(raw_line):
            has_prior_day = any(looks_like_day_line(line) for line in lines[:index])
            next_day_index = next((offset for offset in range(index + 1, len(lines)) if looks_like_day_line(lines[offset])), None)
            if not has_prior_day and next_day_index is not None:
                return "\n".join(lines[next_day_index:]).strip() + "\n", "\n".join(lines[index:next_day_index]).strip()
            return "\n".join(lines[:index]).strip() + "\n", "\n".join(lines[index:]).strip()
    for index, raw_line in enumerate(lines):
        if looks_like_day_line(raw_line):
            leading_text = "\n".join(lines[:index]).strip()
            if leading_text and re.search(r"两大|成人|儿童|电车|电价|电耗|酒店|住宿|餐费|餐饮|景区|景点|门票", leading_text):
                return "\n".join(lines[index:]).strip() + "\n", leading_text
            break
    return text, ""


def parse_passenger_counts(text: str) -> dict[str, int]:
    passengers = {"adults": 1, "children_under_1_2m": 0, "children_over_1_2m": 0}
    compact_party_match = re.search(
        r"([0-9一二两俩三四五六七八九十]+)\s*大\s*([0-9一二两俩三四五六七八九十]+)\s*小([^。；;\n]*)",
        text,
    )
    if compact_party_match:
        passengers["adults"] = parse_small_count(compact_party_match.group(1)) or passengers["adults"]
        child_count = parse_small_count(compact_party_match.group(2)) or 0
        context = compact_party_match.group(3)
        if re.search(r"(?:低于|小于|不到|不足|以下|免票).*1\.?2|1\.?2.*(?:以下|低于|小于|不到|不足|免票)", context):
            passengers["children_under_1_2m"] = child_count
        elif re.search(r"(?:高于|超过|大于|以上).*1\.?2|1\.?2.*(?:以上|高于|超过|大于|半价)", context):
            passengers["children_over_1_2m"] = child_count
        else:
            passengers["children_over_1_2m"] = child_count
        return passengers

    adult_match = re.search(r"([0-9一二两俩三四五六七八九十]+)\s*(?:大|个成人|位成人|成人)", text)
    if adult_match:
        passengers["adults"] = parse_small_count(adult_match.group(1)) or passengers["adults"]

    for child_match in re.finditer(r"([0-9一二两俩三四五六七八九十]+)\s*(?:小|个儿童|名儿童|位儿童|儿童|孩子|小孩)([^。；;\n]*)", text):
        count = parse_small_count(child_match.group(1)) or 0
        context = child_match.group(2)
        if re.search(r"(?:低于|小于|不到|不足|以下|免票).*1\.?2|1\.?2.*(?:以下|低于|小于|不到|不足|免票)", context):
            passengers["children_under_1_2m"] += count
        elif re.search(r"(?:高于|超过|大于|以上).*1\.?2|1\.?2.*(?:以上|高于|超过|大于|半价)", context):
            passengers["children_over_1_2m"] += count
        elif "半价" in context:
            passengers["children_over_1_2m"] += count
        elif "免票" in context:
            passengers["children_under_1_2m"] += count
        else:
            passengers["children_over_1_2m"] += count
    return passengers


def parse_first_amount(patterns: list[str], text: str) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def amount_prefix_pattern() -> str:
    return r"(?:(?:约\s*人民币|人民币|约为|大约|大概|约)\s*)?"


def amount_suffix_pattern() -> str:
    return r"(?:\s*(?:左右|上下))?"


def numeric_range_pattern() -> str:
    number = r"[0-9]+(?:\.[0-9]+)?"
    return rf"{amount_prefix_pattern()}{number}\s*(?:-|~|—|–|至|到)\s*{number}"


def yuan_range_pattern() -> str:
    return rf"{numeric_range_pattern()}\s*元{amount_suffix_pattern()}"


def has_yuan_range(text: str) -> bool:
    return bool(re.search(yuan_range_pattern(), text))


def ambiguous_range_warnings(text: str) -> list[str]:
    warnings = []
    range_value = yuan_range_pattern()
    if re.search(rf"(?:酒店|住宿)[^。；;\n]*?(?:每晚|一晚|每夜)[^。；;\n]*?{range_value}", text):
        warnings.append("Hotel budget range was provided; use a single nightly amount or --hotel-nightly for totals.")
    if re.search(rf"(?:餐费|吃饭|餐饮)[^。；;\n]*?(?:每天|每日|一天)[^。；;\n]*?{range_value}", text):
        warnings.append("Meal budget range was provided; use a single daily amount or --meal-daily for totals.")
    if re.search(rf"电价[^。；;\n]*?{range_value}\s*/?\s*(?:度|kwh|KWH)", text):
        warnings.append("EV electricity price range was provided; use a single CNY/kWh amount or --ev-kwh-price for totals.")
    consumption_range = numeric_range_pattern()
    if re.search(rf"百公里(?:综合)?(?:电耗|耗电)[^。；;\n]*?{consumption_range}\s*(?:度|kwh|KWH){amount_suffix_pattern()}", text):
        warnings.append("EV consumption range was provided; use a single kWh/100km amount or --ev-kwh-per-100km for totals.")
    if re.search(rf"(?:景点|景区|门票|成人票|票价|摆渡车|观光车|区间车|保险)[^。；;\n]*?{range_value}", text):
        warnings.append("Attraction or component fee range was provided; use a single amount or --attraction for totals.")
    if re.search(rf"(?:其他费用|其他|停车|杂费)[^。；;\n]*?{range_value}", text):
        warnings.append("Misc fee range was provided; use a single amount or --misc-fee for totals.")
    return warnings


def clean_fee_name(value: str) -> str:
    return re.sub(r"^(?:已确认景区价格|自动查价补充|查价补充|景点门票|景点费用|景区|门票|票价|费用|费)[：:]?", "", value).strip(" ：:，,、；;。（）()")


def split_fee_fragments(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[，,、；;。]\s*", value) if part.strip()]


def parse_attraction_fee_items(line: str) -> list[dict[str, Any]]:
    clean = re.sub(r"^(?:景点费用|景点门票|门票)\s*[:：]\s*", "", line.strip())
    items: list[dict[str, Any]] = []
    grouped: dict[str, dict[str, Any]] = {}
    current_place: str | None = None

    def attraction_group(name: str) -> dict[str, Any]:
        normalized = clean_fee_name(re.sub(r"(?:成人票|门票|票价|费用|费)$", "", name))
        if normalized not in grouped:
            grouped[normalized] = {"name": normalized, "components": []}
            items.append(grouped[normalized])
        return grouped[normalized]

    for fragment in split_fee_fragments(clean):
        if has_yuan_range(fragment):
            continue

        free_match = re.search(r"(.+?)(?:成人票|门票|票价)?\s*(?:不要钱|免费|免票|(?<![0-9.])0\s*元)", fragment)
        if free_match:
            current_place = clean_fee_name(re.sub(r"(?:成人票|门票|票价)$", "", free_match.group(1)))
            group = attraction_group(current_place)
            group["components"].append({"label": "门票", "unit_price_cny": 0.0, "charge": "free"})
            continue

        ticket_match = re.search(r"(.+?)(?:成人票|门票|票价)\s*([0-9]+(?:\.[0-9]+)?)\s*元", fragment)
        if ticket_match:
            current_place = clean_fee_name(ticket_match.group(1))
            items.append({"name": current_place, "adult_price_cny": float(ticket_match.group(2))})
            continue

        per_person_match = re.search(r"(.+?)\s*([0-9]+(?:\.[0-9]+)?)\s*元\s*(?:一人|/人|每人|每位|一位|人)", fragment)
        if per_person_match:
            label = clean_fee_name(per_person_match.group(1))
            price = float(per_person_match.group(2))
            group_name = current_place or label
            group = attraction_group(group_name)
            group["components"].append({"label": label, "unit_price_cny": price, "charge": "per_person"})
            continue

        generic_match = re.search(r"(.+?)\s*([0-9]+(?:\.[0-9]+)?)\s*元", fragment)
        if generic_match:
            name = clean_fee_name(generic_match.group(1))
            amount = float(generic_match.group(2))
            items.append({"name": name, "adult_price_cny": amount})

    return [item for item in items if item.get("name")]


def attraction_fee_text_from_line(line: str) -> str:
    fragments = split_fee_fragments(line)
    picked: list[str] = []
    collecting = False
    for fragment in fragments:
        if re.search(r"其他费用|其他|杂费", fragment):
            if collecting:
                break
            continue
        if re.search(r"景点|门票|成人票|票价|景区|摆渡车|观光车|区间车|保险", fragment):
            collecting = True
        if collecting:
            picked.append(fragment)
    return "，".join(picked)


def misc_fee_text_from_line(line: str) -> str:
    fragments = split_fee_fragments(line)
    picked: list[str] = []
    collecting = False
    for fragment in fragments:
        if collecting and re.search(r"景点|门票|成人票|票价|景区", fragment):
            break
        if re.search(r"其他费用|其他|停车|杂费", fragment):
            collecting = True
        if collecting:
            picked.append(fragment)
    return "，".join(picked)


def parse_budget_fee_items(line: str, category: str) -> list[dict[str, Any]]:
    """Parse fee fragments like ``小七孔 120 元，中国天眼 140 元``."""
    clean = re.sub(r"^(?:景点费用|景点门票|门票|其他费用|其他|杂费)\s*[:：]\s*", "", line.strip())
    if category == "attraction":
        attraction_text = attraction_fee_text_from_line(line)
        return parse_attraction_fee_items(attraction_text or line)
    if category == "misc":
        misc_text = misc_fee_text_from_line(line)
        clean = re.sub(r"^(?:其他费用|其他|杂费)\s*[:：]\s*", "", (misc_text or line).strip())

    items: list[dict[str, Any]] = []
    for fragment in split_fee_fragments(clean):
        if has_yuan_range(fragment):
            continue
        match = re.search(r"(.+?)\s*([0-9]+(?:\.[0-9]+)?)\s*元", fragment)
        if not match:
            continue
        name = match.group(1).strip(" ，,、；;。")
        if not name:
            continue
        amount = float(match.group(2))
        items.append({"name": name, "amount_cny": amount})
    return items


def parse_budget_text(text: str) -> dict[str, Any]:
    budget_text = text.strip()
    if not budget_text:
        return {}

    result: dict[str, Any] = {
        "passengers": parse_passenger_counts(budget_text),
        "attractions": [],
        "misc_fees": [],
        "warnings": ambiguous_range_warnings(budget_text),
    }
    if re.search(r"电车|新能源|充电|电价|电耗", budget_text):
        result["vehicle_type"] = "ev"

    number = r"([0-9]+(?:\.[0-9]+)?)"
    amount_prefix = amount_prefix_pattern()
    amount_suffix = amount_suffix_pattern()

    ev_price = parse_first_amount(
        [rf"电价\s*{amount_prefix}{number}\s*元?{amount_suffix}\s*/?\s*(?:度|kwh|KWH)"],
        budget_text,
    )
    if ev_price is not None:
        result["ev_kwh_price"] = ev_price

    ev_consumption = parse_first_amount(
        [
            rf"百公里(?:综合)?(?:电耗|耗电)\s*{amount_prefix}{number}\s*(?:度|kwh|KWH){amount_suffix}",
            rf"{amount_prefix}{number}\s*(?:度|kwh|KWH){amount_suffix}\s*/?\s*(?:百公里|100\s*km)",
        ],
        budget_text,
    )
    if ev_consumption is not None:
        result["ev_kwh_per_100km"] = ev_consumption

    hotel_nightly = parse_first_amount(
        [rf"(?:酒店|住宿)[^。；;\n]*?(?:每晚|一晚|每夜)\s*{amount_prefix}{number}\s*元{amount_suffix}"],
        budget_text,
    )
    if hotel_nightly is not None:
        result["hotel_nightly"] = hotel_nightly

    meal_daily = parse_first_amount(
        [rf"(?:餐费|吃饭|餐饮)[^。；;\n]*?(?:每天|每日|一天)\s*{amount_prefix}{number}\s*元{amount_suffix}"],
        budget_text,
    )
    if meal_daily is not None:
        result["meal_daily"] = meal_daily

    for raw_line in budget_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.search(r"景点|景区|门票|成人票|票价|免费|免票", line):
            result["attractions"].extend(parse_budget_fee_items(line, "attraction"))
        if re.search(r"其他费用|其他|停车|杂费", line):
            result["misc_fees"].extend(parse_budget_fee_items(line, "misc"))

    return result


def trip_day_count(data: dict[str, Any]) -> int:
    max_day = 0
    for day in data.get("days", []):
        match = re.search(r"(\d+)", day.get("day", ""))
        if match:
            max_day = max(max_day, int(match.group(1)))
    return max(max_day, len(data.get("days", [])))


def budget_item(
    category: str,
    label: str,
    amount: float,
    detail: str = "",
    quantity: float | None = None,
    unit_price: float | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "category": category,
        "label": label,
        "amount_cny": round(float(amount), 2),
    }
    if detail:
        item["detail"] = detail
    if quantity is not None:
        item["quantity"] = float(quantity)
    if unit_price is not None:
        item["unit_price_cny"] = float(unit_price)
    return item


def total_passenger_count(passenger_counts: dict[str, int]) -> int:
    return (
        int(passenger_counts.get("adults", 0))
        + int(passenger_counts.get("children_under_1_2m", 0))
        + int(passenger_counts.get("children_over_1_2m", 0))
    )


def build_budget(
    data: dict[str, Any],
    vehicle_type: str = "none",
    ev_kwh_price: float | None = None,
    ev_kwh_per_100km: float | None = None,
    hotel_nightly: float | None = None,
    hotel_nights: int | None = None,
    meal_daily: float | None = None,
    meal_days: int | None = None,
    attractions: list[dict[str, Any]] | None = None,
    misc_fees: list[dict[str, Any]] | None = None,
    passengers: dict[str, int] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    totals = data.get("totals", {})
    distance_km = float(totals.get("distance_km") or 0)
    day_count = trip_day_count(data)
    items: list[dict[str, Any]] = []
    assumptions: dict[str, Any] = {
        "trip_days": day_count,
        "distance_km": round(distance_km, 1),
    }
    passenger_counts = {
        "adults": 1,
        "children_under_1_2m": 0,
        "children_over_1_2m": 0,
    }
    if passengers:
        passenger_counts.update({key: int(value) for key, value in passengers.items() if key in passenger_counts})
    assumptions["passengers"] = passenger_counts
    budget_warnings: list[str] = []
    for warning in warnings or []:
        warning_text = str(warning)
        if warning_text and warning_text not in budget_warnings:
            budget_warnings.append(warning_text)

    toll_cny = float(totals.get("toll_cny") or 0)
    if toll_cny:
        items.append(
            budget_item(
                "toll",
                "过路费",
                toll_cny,
                f"全程 {compact_number_label(distance_km)} 公里 · 来自路线数据",
            )
        )

    if vehicle_type == "ev":
        if ev_kwh_price is not None and ev_kwh_per_100km is not None:
            kwh = distance_km * ev_kwh_per_100km / 100
            energy_amount = kwh * ev_kwh_price
            assumptions["vehicle"] = {
                "type": "ev",
                "kwh_price_cny": ev_kwh_price,
                "kwh_per_100km": ev_kwh_per_100km,
                "estimated_kwh": round(kwh, 1),
            }
            items.append(
                budget_item(
                    "vehicle_energy",
                    "电车补能",
                    energy_amount,
                    f"全程 {compact_number_label(distance_km)} 公里 × {compact_number_label(ev_kwh_per_100km)} 度/百公里 = {compact_number_label(kwh)} 度 × {unit_money_label(ev_kwh_price)}/度",
                    quantity=kwh,
                    unit_price=ev_kwh_price,
                )
            )
        else:
            budget_warnings.append("Vehicle is EV but --ev-kwh-price or --ev-kwh-per-100km is missing; energy cost skipped.")
    elif vehicle_type != "none":
        budget_warnings.append(f"Unsupported vehicle type for budget: {vehicle_type}")

    if hotel_nightly is not None:
        nights = hotel_nights if hotel_nights is not None else max(day_count - 1, 0)
        assumptions["hotel"] = {"nightly_cny": hotel_nightly, "nights": nights}
        items.append(
            budget_item("hotel", "住宿", hotel_nightly * nights, f"{nights} 晚 × {money_label(hotel_nightly)}/晚", quantity=nights, unit_price=hotel_nightly)
        )

    if meal_daily is not None:
        days = meal_days if meal_days is not None else day_count
        assumptions["meal"] = {"daily_cny": meal_daily, "days": days}
        items.append(
            budget_item("meal", "餐饮", meal_daily * days, f"{days} 天 × {money_label(meal_daily)}/天", quantity=days, unit_price=meal_daily)
        )

    for item in attractions or []:
        if "components" in item:
            people = total_passenger_count(passenger_counts)
            component_total = 0.0
            detail_parts = []
            rendered_components = []
            for component in item.get("components") or []:
                label = str(component.get("label") or "费用")
                unit_price = float(component.get("unit_price_cny") or 0)
                charge = str(component.get("charge") or "per_person")
                if charge == "free" or unit_price == 0:
                    amount = 0.0
                    detail_parts.append(f"{label}免费")
                    quantity = 0
                else:
                    quantity = people
                    amount = quantity * unit_price
                    detail_parts.append(f"{label} {quantity} × {unit_money_label(unit_price)}")
                component_total += amount
                rendered_components.append({
                    "label": label,
                    "unit_price_cny": round(unit_price, 2),
                    "quantity": quantity,
                    "amount_cny": round(amount, 2),
                    "charge": charge,
                })
            item_data = budget_item("attraction", item["name"], component_total, "；".join(detail_parts))
            item_data["components"] = rendered_components
            items.append(item_data)
        elif "adult_price_cny" in item:
            adult_price = float(item["adult_price_cny"])
            adults = passenger_counts["adults"]
            free_children = passenger_counts["children_under_1_2m"]
            half_children = passenger_counts["children_over_1_2m"]
            amount = adults * adult_price + half_children * adult_price * 0.5
            detail_parts = [f"成人 {adults} × {money_label(adult_price)}"]
            if half_children:
                detail_parts.append(f"1.2m 以上儿童 {half_children} × {money_label(adult_price * 0.5)}")
            if free_children:
                detail_parts.append(f"1.2m 以下儿童 {free_children} 人免票")
            item_data = budget_item("attraction", item["name"], amount, "；".join(detail_parts))
            item_data["adult_price_cny"] = round(adult_price, 2)
            item_data["charged_adults"] = adults
            item_data["free_children_under_1_2m"] = free_children
            item_data["half_price_children_over_1_2m"] = half_children
            items.append(item_data)
        else:
            items.append(budget_item("attraction", item["name"], item["amount_cny"], "景点费用"))

    for item in misc_fees or []:
        items.append(budget_item("misc", item["name"], item["amount_cny"], "其他费用"))

    category_totals: dict[str, float] = {}
    for item in items:
        category = str(item["category"])
        category_totals[category] = round(category_totals.get(category, 0) + float(item["amount_cny"]), 2)

    total_cny = round(sum(float(item["amount_cny"]) for item in items), 2)
    missing_attractions = missing_attraction_candidates(data, items)
    configured = any(
        value is not None and value != []
        for value in (ev_kwh_price, ev_kwh_per_100km, hotel_nightly, meal_daily, attractions, misc_fees)
    ) or vehicle_type != "none"
    budget_warnings = list(dict.fromkeys(warning.strip() for warning in budget_warnings if warning.strip()))
    return {
        "currency": "CNY",
        "configured": bool(configured),
        "total_cny": total_cny,
        "category_totals": category_totals,
        "items": items,
        "missing_attractions": missing_attractions,
        "assumptions": assumptions,
        "warnings": budget_warnings,
    }


def ensure_budget(data: dict[str, Any]) -> None:
    if "budget" not in data:
        data["budget"] = build_budget(data)


SCENIC_SPOT_ALIASES = [
    {
        "name": "荔波小七孔景区",
        "aliases": ["小七孔", "荔波小七孔", "荔波小七孔景区"],
    },
    {
        "name": "中国天眼景区",
        "aliases": ["中国天眼", "天眼", "天眼景区", "中国天眼景区"],
    },
    {
        "name": "黄果树瀑布景区",
        "aliases": ["黄果树", "黄果树瀑布", "黄果树瀑布景区"],
    },
    {
        "name": "韶山景区",
        "aliases": ["韶山", "韶山景区"],
    },
    {
        "name": "凤凰古城",
        "aliases": ["凤凰古城"],
    },
]


def budget_category_label(category: str) -> str:
    return BUDGET_CATEGORY_LABELS.get(category, category)


def normalize_place_name(value: Any) -> str:
    return re.sub(r"[\s·・\-—_（）()]+", "", str(value or "")).lower()


def scenic_rule_for_name(name: str) -> dict[str, Any] | None:
    normalized = normalize_place_name(name)
    if not normalized:
        return None
    for rule in SCENIC_SPOT_ALIASES:
        names = [rule["name"], *(rule.get("aliases") or [])]
        for alias in names:
            alias_normalized = normalize_place_name(alias)
            if alias_normalized and alias_normalized in normalized:
                return rule
    return None


def route_scenic_candidates(data: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}

    def add(place_name: str, day_label: str) -> None:
        rule = scenic_rule_for_name(place_name)
        if not rule:
            return
        canonical = str(rule["name"])
        candidate = candidates.setdefault(
            canonical,
            {
                "name": canonical,
                "matched_names": [],
                "days": [],
                "suggestion": f"可在费用预算中补充：{canonical}成人票 价格 元。",
            },
        )
        if place_name not in candidate["matched_names"]:
            candidate["matched_names"].append(place_name)
        if day_label and day_label not in candidate["days"]:
            candidate["days"].append(day_label)

    for day in data.get("days", []):
        day_label = str(day.get("day") or "")
        for leg in day.get("legs") or []:
            add(str(leg.get("from") or ""), day_label)
            add(str(leg.get("to") or ""), day_label)
        for note in day.get("notes") or []:
            add(str(note), day_label)
    return list(candidates.values())


def missing_attraction_candidates(data: dict[str, Any], budget_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    configured = set()
    for item in budget_items:
        if item.get("category") != "attraction":
            continue
        label = str(item.get("label") or "")
        rule = scenic_rule_for_name(label)
        configured.add(str(rule["name"]) if rule else label)

    missing = []
    for candidate in route_scenic_candidates(data):
        if candidate["name"] not in configured:
            missing.append(candidate)
    return missing
