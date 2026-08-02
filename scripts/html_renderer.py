#!/usr/bin/env python3
"""Render mobile-friendly trip itinerary HTML."""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from budget import budget_category_label, ensure_budget, money_label
import leaflet_map


def _round_to_step(value: float, step: int = 5) -> int:
    """Round ``value`` to the nearest multiple of ``step`` (e.g. 5).

    Used for display-friendly distances/durations: 593.1km -> 595km,
    34 min -> 35 min. Applied only at the display layer; the stored data in
    trip-data.json keeps its original precision.
    """
    if step <= 0:
        return int(round(value))
    return int(round(float(value) / step) * step)


def distance_label(km: float | int) -> str:
    """Display a distance rounded to the nearest 5 km (595km, not 593.1km)."""
    return f"{_round_to_step(km, 5)}km"


def duration_label(minutes: int) -> str:
    # Round to nearest 5 min for readability (6h34m -> 6h35m).
    minutes = _round_to_step(minutes, 5)
    hours = minutes // 60
    mins = minutes % 60
    if hours and mins:
        return f"{hours}h{mins:02d}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


WEEKDAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def parse_start_date(value: str | None) -> Any:
    """Parse a YYYY-MM-DD string into a date, or return None if invalid/empty."""
    if not value:
        return None
    import datetime
    try:
        return datetime.date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def day_date_label(day_label: str, start_date: Any) -> str:
    """Return a calendar label for a day block, e.g. '7月17日 周四'.

    ``day_label`` is like 'D5'; the offset is parsed from the number. When
    ``start_date`` is None the function returns "" (no date shown).
    """
    if not start_date:
        return ""
    import datetime
    m = re.search(r"(\d+)", day_label or "")
    if not m:
        return ""
    offset = int(m.group(1)) - 1  # D1 is the start date itself
    the_date = start_date + datetime.timedelta(days=offset)
    weekday = WEEKDAY_LABELS[the_date.weekday()]
    return f"{the_date.month}月{the_date.day}日 {weekday}"


def trip_date_range(days: list[dict[str, Any]], start_date: Any) -> str:
    """Return a compact trip date range like '7.17-7.26' or '' if no start date.

    Uses the highest day number across all day blocks as the last day, so
    stay-only days are counted too.
    """
    if not start_date:
        return ""
    import datetime
    max_offset = 0
    for day in days:
        m = re.search(r"(\d+)", day.get("day", ""))
        if m:
            max_offset = max(max_offset, int(m.group(1)) - 1)
    last_date = start_date + datetime.timedelta(days=max_offset)
    if last_date == start_date:
        return f"{start_date.month}.{start_date.day}"
    return f"{start_date.month}.{start_date.day}-{last_date.month}.{last_date.day}"

def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def ordered_stops(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stops: list[dict[str, Any]] = []

    def add(name: str, point: dict[str, float] | None) -> None:
        if stops and stops[-1]["name"] == name:
            return
        stops.append({"name": name, "point": point})

    for day in days:
        for index, leg in enumerate(day["legs"]):
            if index == 0:
                add(leg["from"], leg.get("origin"))
            add(leg["to"], leg.get("destination"))
    return stops


def generate_html(
    data: dict[str, Any],
    path: Path,
    map_file: str | None = None,
    budget_image_file: str | None = None,
) -> None:
    ensure_budget(data)
    days_html = []
    overview_html = []
    dots_html = []
    budget_rows = []
    start_date = parse_start_date(data.get("start_date"))
    for day in data["days"]:
        date_label = day_date_label(day["day"], start_date)
        leg_items = []
        if not day["legs"]:
            note_text = " / ".join(day.get("notes") or [day["title"]])
            leg_items.append(
                f'''<div class="item">
  <span class="item-icon"><i data-lucide="map-pin"></i></span>
  <div class="item-body">
    <div class="item-label">市区停留</div>
    <div class="item-text">{escape(note_text)}</div>
  </div>
  <div class="item-right">不计入<br>城际驾车</div>
</div>'''
            )
        else:
            for leg in day["legs"]:
                est = " · 估算" if leg.get("estimated") else ""
                leg_items.append(
                    f'''<div class="item">
  <span class="item-icon"><i data-lucide="car"></i></span>
  <div class="item-body">
    <div class="item-label">驾车{escape(est)}</div>
    <div class="item-text">{escape(leg["from"])} → {escape(leg["to"])}</div>
  </div>
  <div class="item-right">{escape(distance_label(leg["distance_km"]))} · {escape(duration_label(int(leg["duration_min"])))}<br>{escape(money_label(leg.get("toll_cny")))}</div>
</div>'''
                )

        days_html.append(
            f'''<section class="slide" aria-label="{escape(day["day"])} {escape(day["title"])}">
  <div class="day-card">
    <div class="day-top">
      <div class="day-num">{escape(day["day"])}{(' · ' + date_label) if date_label else ''}</div>
      <div class="day-title">{escape(day["title"])}</div>
    </div>
    <div class="items">{''.join(leg_items)}</div>
    <div class="day-foot">
      <div class="stat"><div class="stat-num">{escape(distance_label(day["distance_km"]))}</div><div class="stat-lbl">公里</div></div>
      <div class="stat"><div class="stat-num">{escape(duration_label(int(day["duration_min"])))}</div><div class="stat-lbl">驾车</div></div>
      <div class="stat"><div class="stat-num">{escape(money_label(day["toll_cny"]))}</div><div class="stat-lbl">过路费</div></div>
    </div>
  </div>
</section>'''
        )
        dots_html.append(
            f'''<button class="pager-dot" type="button" data-slide="{len(dots_html)}" aria-label="切换到 {escape(day["day"])}"></button>'''
        )

        overview_html.append(
            f'''<div class="ov-day-card">
  <div class="ov-day-head">
    <span class="ov-day-tag">{escape(day["day"])}</span>
    <span class="ov-day-route">{escape(day["title"])}</span>
    <span class="ov-day-dist">{escape(distance_label(day["distance_km"]))}</span>
  </div>
  <div class="ov-day-body">
    <div class="ov-line"><span class="ui-icon-text"><i data-lucide="clock"></i><span>{escape(duration_label(int(day["duration_min"])))}</span></span></div>
    <div class="ov-line"><span class="ui-icon-text"><i data-lucide="banknote"></i><span>{escape(money_label(day["toll_cny"]))}</span></span></div>
  </div>
</div>'''
        )

    totals = data["totals"]
    budget = data.get("budget") or {}
    budget_total = float(budget.get("total_cny") or 0)
    budget_configured = bool(budget.get("configured"))
    missing_attractions = budget.get("missing_attractions") or []
    rendered_budget_items: list[dict[str, Any]] = []
    rendered_budget_index: dict[tuple[str, str], dict[str, Any]] = {}
    for item in budget.get("items") or []:
        category = str(item.get("category") or "")
        label = str(item.get("label") or "")
        if category == "attraction":
            key = (category, label)
            if key in rendered_budget_index:
                existing = rendered_budget_index[key]
                existing["amount_cny"] = round(float(existing.get("amount_cny") or 0) + float(item.get("amount_cny") or 0), 2)
                detail = str(item.get("detail") or "").strip()
                if detail:
                    existing["detail"] = "；".join([part for part in [existing.get("detail"), detail] if part])
                continue
            copy_item = dict(item)
            rendered_budget_index[key] = copy_item
            rendered_budget_items.append(copy_item)
            continue
        rendered_budget_items.append(item)

    for item in rendered_budget_items:
        detail = item.get("detail") or budget_category_label(str(item.get("category") or ""))
        budget_rows.append(
            f'''<div class="budget-row">
  <div class="budget-left">
    <div class="budget-label">{escape(item.get("label", ""))}</div>
    <div class="budget-detail">{escape(detail)}</div>
  </div>
  <div class="budget-amount">{escape(money_label(item.get("amount_cny")))}</div>
</div>'''
        )
    missing_attraction_rows = []
    for candidate in missing_attractions:
        day_text = "、".join(candidate.get("days") or [])
        matched_text = "、".join(candidate.get("matched_names") or [])
        detail_parts = []
        if day_text:
            detail_parts.append(day_text)
        if matched_text and matched_text != candidate.get("name"):
            detail_parts.append(f"路线写法：{matched_text}")
        detail_parts.append("未计入总预算")
        missing_attraction_rows.append(
            f'''<div class="budget-missing-row">
  <div>
    <div class="budget-missing-name">{escape(candidate.get("name", ""))}</div>
    <div class="budget-missing-detail">{escape(" · ".join(detail_parts))}</div>
  </div>
  <div class="budget-missing-action">{escape(candidate.get("suggestion", "请补充门票/景交费用。"))}</div>
</div>'''
        )
    missing_attraction_panel = ""
    if missing_attraction_rows:
        missing_attraction_panel = f'''<div class="budget-missing">
  <div class="budget-missing-title"><span class="ui-icon-text"><i data-lucide="circle-alert"></i><span>待补景点费用</span></span></div>
  <div class="budget-missing-text">检测到以下景区，但费用预算里还没有配置门票或景交费用，因此没有计入总额。</div>
  <div class="budget-missing-list">{''.join(missing_attraction_rows)}</div>
</div>'''
    budget_image_action = ""
    if budget_image_file and (path.parent / budget_image_file).exists():
        budget_image_action = (
            f'<a class="budget-image-link ui-icon-text" href="./{escape(budget_image_file)}" download>'
            '<i data-lucide="image-down"></i><span>下载费用清单图</span></a>'
        )
    if not budget_configured:
        budget_panel = f'''<div class="activate-card">
  <span class="activate-icon"><i data-lucide="calculator"></i></span>
  <div class="activate-body">
    <div class="activate-title">费用计算未启用</div>
    <div class="activate-text">运行时加入电费、住宿、餐饮或景点费用参数后，这里会生成总预算和分项明细。</div>
    <div class="activate-example">你可以这样说：我们是两大一小（低于 1.2m），开电车，电价 1.5 元/度，百公里电耗 16 度；酒店每晚 300 元，餐费每天 100 元；天眼景区门票不要钱，摆渡车 50 元一人，保险 10 元一人。</div>
  </div>
</div>
<div class="budget-muted">
  <span class="ui-icon-text"><i data-lucide="banknote"></i><span>当前路线过路费参考：{escape(money_label(totals.get("toll_cny")))}</span></span>
</div>
{missing_attraction_panel}'''
    else:
        budget_panel = f'''<div class="budget-summary">
  <div>
    <div class="budget-kicker">费用预估</div>
    <div class="budget-total">{escape(money_label(budget_total))}</div>
  </div>
  <div class="budget-summary-side">
    <div class="budget-note">按当前输入参数粗略计算，实际价格请以预订和现场为准。</div>
    {budget_image_action}
  </div>
</div>
<div class="budget-list">{''.join(budget_rows)}</div>
{missing_attraction_panel}'''
    title = escape(data["title"])
    _sd = parse_start_date(data.get("start_date"))
    _range = trip_date_range(data["days"], _sd) if _sd else ""
    title_with_date = f"{title} · {_range}" if _range else title
    route_summary = " → ".join(stop["name"] for stop in ordered_stops(data["days"]))
    any_estimated = any(leg.get("estimated") for day in data["days"] for leg in day["legs"])
    toll_hint = "估算参考" if any_estimated else "地图数据"
    overview_cost_label = "总费用" if budget_configured else "过路费"
    overview_cost_value = budget_total if budget_configured else totals["toll_cny"]
    overview_cost_hint = "含过路费等" if budget_configured else toll_hint
    # Interactive Leaflet map snippet (real driving route, inline data).
    leaflet_snippet = leaflet_map.build_leaflet_snippet(data)
    day_titles_json = leaflet_map.json_for_script([day["title"] for day in data["days"]])
    trip_start_date_json = leaflet_map.json_for_script(data.get("start_date"))
    # Optional: link to the standalone PNG if it was generated.
    png_link = ""
    if map_file and (path.parent / map_file).exists():
        png_link = f'<div class="map-note">真实路线地图 · 可缩放拖动 · 点击路段看详情 · <a href="./{escape(map_file)}" target="_blank" rel="noopener">查看路线图</a></div>'
    else:
        png_link = f'<div class="map-note">真实路线地图 · 可缩放拖动 · 点击路段看详情</div>'
    html_text = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>{title}</title>
<script src="https://unpkg.com/lucide@latest"></script>
<style>
:root {{
  --primary: #2C6BB2;
  --bg: #F6F8FA;
  --card: #FFFFFF;
  --accent: #D97036;
  --green: #25945B;
  --text: #26313B;
  --text2: #7B8490;
  --line: #E9EDF2;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }}
html, body {{ min-height: 100%; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  font-size: 14px;
}}
svg {{ stroke-width: 2; }}
.app {{ width: 100%; max-width: 520px; margin: 0 auto; min-height: 100vh; display: flex; flex-direction: column; }}
/* Responsive: widen on larger screens (mobile-first baseline is 520px). */
@media (min-width: 768px) {{ .app {{ max-width: 760px; }} .header h1 {{ font-size: 22px; }} }}
@media (min-width: 1024px) {{ .app {{ max-width: 960px; }} }}
.header {{ padding: 16px 20px 10px; flex-shrink: 0; }}
.header h1 {{ font-size: 18px; font-weight: 800; letter-spacing: 0; }}
.subtitle {{ font-size: 11px; color: var(--text2); margin-top: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.tabs {{ display: flex; align-items: center; gap: 6px; padding: 0 20px 10px; overflow-x: auto; scrollbar-width: none; flex-shrink: 0; }}
.tabs::-webkit-scrollbar {{ display: none; }}
.tab {{
  border: 1px solid var(--line);
  background: var(--card);
  color: var(--text2);
  border-radius: 20px;
  padding: 6px 14px;
  font-size: 13px;
  white-space: nowrap;
  cursor: pointer;
}}
.tab.active {{ background: var(--primary); border-color: var(--primary); color: #FFFFFF; font-weight: 700; }}
.main {{ flex: 1; min-height: 0; }}
.tab-panel {{ display: none; padding: 8px 20px 28px; }}
.tab-panel.active {{ display: block; }}
.overview-stack {{ display: grid; gap: 10px; }}
.overview-stats {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }}
.stat-tile {{
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px 10px;
  min-width: 0;
}}
.stat-tile .ui-icon-text {{ color: var(--text2); font-size: 11px; }}
.stat-tile .value {{ margin-top: 7px; color: var(--primary); font-size: 16px; font-weight: 900; line-height: 1.15; word-break: break-word; }}
.stat-tile .hint {{ margin-top: 2px; color: var(--text2); font-size: 10px; }}
.day-pager {{ display: grid; gap: 10px; }}
.pager-head {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; }}
.pager-title {{ min-width: 0; }}
.pager-kicker {{ font-size: 11px; color: var(--text2); }}
.pager-current {{ margin-top: 2px; font-size: 16px; font-weight: 800; color: var(--text); word-break: break-word; }}
.pager-actions {{ display: inline-flex; align-items: center; gap: 8px; flex-shrink: 0; }}
.pager-button {{
  width: 34px;
  height: 34px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--card);
  color: var(--primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}}
.pager-button:focus-visible, .tab:focus-visible {{ outline: 2px solid color-mix(in srgb, var(--primary) 60%, white); outline-offset: 2px; }}
.pager-button svg {{ width: 17px; height: 17px; flex-shrink: 0; }}
.slider {{
  display: flex;
  gap: 12px;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  scroll-behavior: smooth;
  scrollbar-width: none;
  touch-action: pan-x;
}}
.slider::-webkit-scrollbar {{ display: none; }}
.slide {{ flex: 0 0 100%; min-width: 0; scroll-snap-align: start; }}
.pager-dots {{ display: flex; align-items: center; justify-content: center; gap: 6px; min-height: 18px; }}
.pager-dot {{
  width: 7px;
  height: 7px;
  border: 0;
  border-radius: 999px;
  background: #C9D2DE;
  cursor: pointer;
}}
.pager-dot.active {{ width: 20px; background: var(--primary); }}
.day-card, .ov-day-card, .t-card, .big-card, .map-card {{
  background: var(--card);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 8px rgba(20, 33, 48, 0.05);
}}
.day-top {{ padding: 18px 18px 14px; border-bottom: 1px solid var(--line); }}
.day-num {{ font-size: 12px; color: var(--primary); font-weight: 800; }}
.day-title {{ font-size: 17px; font-weight: 800; margin-top: 3px; word-break: break-word; }}
.day-date {{ font-size: 12px; color: var(--text2); margin-top: 3px; }}
.item {{ display: flex; align-items: flex-start; gap: 12px; padding: 13px 18px; border-bottom: 1px solid var(--line); }}
.item:last-child {{ border-bottom: 0; }}
.item-icon {{ width: 22px; display: flex; justify-content: center; padding-top: 2px; flex-shrink: 0; }}
.item-icon svg, .ui-icon-text svg {{ width: 16px; height: 16px; flex-shrink: 0; }}
.item-icon svg {{ stroke: var(--primary); }}
.item-body {{ flex: 1; min-width: 0; }}
.item-label {{ font-size: 11px; color: var(--text2); }}
.item-text {{ font-size: 13px; word-break: break-word; }}
.item-right {{ flex-shrink: 0; text-align: right; font-size: 11px; color: var(--text2); line-height: 1.45; }}
.day-foot {{ display: flex; align-items: center; gap: 8px; padding: 13px 18px; background: #FAFBFC; border-top: 1px solid var(--line); }}
.stat {{ flex: 1; text-align: center; min-width: 0; }}
.stat-num {{ font-size: 15px; font-weight: 800; color: var(--primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.stat-lbl {{ font-size: 10px; color: var(--text2); margin-top: 1px; }}
.ov-day-card {{ margin-bottom: 8px; }}
.ov-day-head {{ display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--line); }}
.ov-day-tag {{ font-size: 12px; font-weight: 800; color: var(--primary); min-width: 28px; }}
.ov-day-route {{ flex: 1; min-width: 0; font-size: 14px; font-weight: 700; word-break: break-word; }}
.ov-day-dist {{ font-size: 13px; color: var(--accent); font-weight: 800; flex-shrink: 0; }}
.ov-day-body {{ display: flex; align-items: center; gap: 14px; padding: 9px 16px 12px; color: var(--text2); font-size: 12px; }}
.ui-icon-text {{ display: inline-flex; align-items: center; gap: 6px; min-width: 0; }}
.t-card {{ display: flex; align-items: center; gap: 10px; padding: 14px 16px; margin-bottom: 8px; }}
.t-day {{ font-size: 13px; font-weight: 800; color: var(--primary); min-width: 30px; }}
.t-route {{ flex: 1; min-width: 0; }}
.t-route .name {{ font-size: 13px; word-break: break-word; }}
.t-route .info {{ font-size: 11px; color: var(--text2); }}
.t-fee {{ font-size: 15px; font-weight: 800; color: var(--accent); flex-shrink: 0; }}
.big-card {{ padding: 24px 20px; text-align: center; margin-top: 8px; }}
.big-card .num {{ font-size: 32px; font-weight: 900; color: var(--primary); }}
.big-card .lbl {{ font-size: 12px; color: var(--text2); margin-top: 4px; }}
.map-card {{ padding: 12px; }}
.map-scroll {{ overflow: hidden; }}
.map-scroll a {{ display: block; }}
.leaflet-wrap {{ width: 100%; }}
.leaflet-container {{ font: inherit; }}
.map-note {{ padding: 9px 4px 2px; font-size: 11px; color: var(--text2); text-align: center; }}
.map-note a {{ color: var(--accent, #2c6bb2); }}
.budget-summary, .activate-card {{
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 10px;
}}
.budget-summary {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }}
.budget-kicker {{ color: var(--text2); font-size: 12px; }}
.budget-total {{ margin-top: 3px; color: var(--primary); font-size: 30px; font-weight: 900; line-height: 1.1; }}
.budget-summary-side {{ display: grid; justify-items: end; gap: 8px; min-width: 0; }}
.budget-note {{ max-width: 210px; color: var(--text2); font-size: 11px; text-align: right; }}
.budget-image-link {{ min-height: 34px; padding: 0 10px; border: 1px solid var(--primary); border-radius: 6px; color: var(--primary); background: #FFFFFF; text-decoration: none; font-size: 12px; font-weight: 800; white-space: nowrap; }}
.budget-image-link svg {{ width: 16px; height: 16px; flex-shrink: 0; }}
.budget-image-link:focus-visible {{ outline: 2px solid color-mix(in srgb, var(--primary) 60%, white); outline-offset: 2px; }}
.budget-list {{ display: grid; gap: 8px; }}
.budget-row {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; }}
.budget-left {{ min-width: 0; }}
.budget-label {{ font-weight: 800; font-size: 14px; word-break: break-word; }}
.budget-detail {{ margin-top: 2px; color: var(--text2); font-size: 11px; word-break: break-word; }}
.budget-amount {{ color: var(--accent); font-size: 16px; font-weight: 900; white-space: nowrap; }}
.budget-missing {{ margin-top: 10px; background: #FFFFFF; border: 1px solid #E4CFC1; border-radius: 8px; padding: 14px; }}
.budget-missing-title {{ color: #A6542C; font-size: 14px; font-weight: 900; }}
.budget-missing-title .ui-icon-text svg {{ width: 16px; height: 16px; flex-shrink: 0; }}
.budget-missing-text {{ margin-top: 6px; color: var(--text2); font-size: 12px; }}
.budget-missing-list {{ display: grid; gap: 8px; margin-top: 10px; }}
.budget-missing-row {{ display: grid; gap: 6px; border-top: 1px solid var(--line); padding-top: 9px; }}
.budget-missing-row:first-child {{ border-top: 0; padding-top: 0; }}
.budget-missing-name {{ font-weight: 800; font-size: 13px; color: var(--text); word-break: break-word; }}
.budget-missing-detail, .budget-missing-action {{ color: var(--text2); font-size: 11px; word-break: break-word; }}
.budget-missing-action {{ color: #A6542C; }}
.activate-card {{ display: flex; align-items: flex-start; gap: 12px; }}
.activate-icon {{ width: 34px; height: 34px; border-radius: 999px; background: color-mix(in srgb, var(--primary) 12%, white); color: var(--primary); display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }}
.activate-icon svg {{ width: 18px; height: 18px; flex-shrink: 0; }}
.activate-body {{ min-width: 0; }}
.activate-title {{ font-size: 15px; font-weight: 900; color: var(--text); }}
.activate-text {{ margin-top: 4px; color: var(--text2); font-size: 12px; }}
.activate-example {{ margin-top: 10px; padding: 10px; border-radius: 8px; background: #F1F4F8; color: #445161; font-size: 11px; line-height: 1.6; word-break: break-word; }}
.budget-muted {{ background: var(--card); border: 1px dashed #D6DEE8; border-radius: 8px; padding: 12px 14px; color: var(--text2); font-size: 12px; }}
@media print {{ .tabs, .pager-actions, .pager-dots, .map-note {{ display: none !important; }} .tab-panel {{ display: block !important; break-inside: avoid; }} .app {{ max-width: none; }} body {{ background: #FFFFFF; }} }}
</style>
</head>
<body>
<div class="app">
  <header class="header">
    <h1>{title_with_date}</h1>
    <div class="subtitle">{escape(route_summary)}</div>
  </header>
  <nav class="tabs" aria-label="行程视图">
    <button class="tab active" data-tab="overview">总览</button>
    <button class="tab" data-tab="daily">行程</button>
    <button class="tab" data-tab="budget">费用</button>
  </nav>
  <main class="main">
    <section class="tab-panel active" id="tab-overview">
      <div class="overview-stack">
        <div class="map-card"><div class="map-scroll">{leaflet_snippet}</div>{png_link}</div>
        <div class="overview-stats">
          <div class="stat-tile"><span class="ui-icon-text"><i data-lucide="route"></i><span>总里程</span></span><div class="value">{escape(distance_label(totals["distance_km"]))}</div><div class="hint">全程驾车</div></div>
          <div class="stat-tile"><span class="ui-icon-text"><i data-lucide="clock"></i><span>总时长</span></span><div class="value">{escape(duration_label(int(totals["duration_min"])))}</div><div class="hint">不含停留</div></div>
          <div class="stat-tile"><span class="ui-icon-text"><i data-lucide="banknote"></i><span>{escape(overview_cost_label)}</span></span><div class="value">{escape(money_label(overview_cost_value))}</div><div class="hint">{escape(overview_cost_hint)}</div></div>
        </div>
        <div>{''.join(overview_html)}</div>
      </div>
    </section>
    <section class="tab-panel" id="tab-daily">
      <div class="day-pager">
        <div class="pager-head">
          <div class="pager-title"><div class="pager-kicker">DAY <span id="pagerIndex">1</span> / {len(data["days"])}</div><div class="pager-current" id="pagerTitle">{escape(data["days"][0]["title"])}</div></div>
          <div class="pager-actions">
            <button class="pager-button" type="button" id="prevDay" aria-label="上一天"><i data-lucide="chevron-left"></i></button>
            <button class="pager-button" type="button" id="nextDay" aria-label="下一天"><i data-lucide="chevron-right"></i></button>
          </div>
        </div>
        <div class="slider" id="daySlider">{''.join(days_html)}</div>
        <div class="pager-dots" id="pagerDots">{''.join(dots_html)}</div>
      </div>
    </section>
    <section class="tab-panel" id="tab-budget">
      {budget_panel}
    </section>
  </main>
</div>
<script>
const dayTitles = {day_titles_json};
const tripStartDate = {trip_start_date_json};  // 'YYYY-MM-DD' or null
const daySlider = document.getElementById('daySlider');
const pagerIndex = document.getElementById('pagerIndex');
const pagerTitle = document.getElementById('pagerTitle');
const pagerDots = Array.from(document.querySelectorAll('.pager-dot'));
let currentDay = 0;
let isProgrammaticScroll = false;

function scrollToCurrentDay(behavior = 'smooth') {{
  if (!daySlider) return;
  window.requestAnimationFrame(() => {{
    const targetSlide = daySlider.children[currentDay];
    if (!targetSlide || !daySlider.clientWidth) return;
    isProgrammaticScroll = true;
    const targetLeft = targetSlide.offsetLeft - daySlider.offsetLeft;
    if (behavior === 'auto') {{
      const previousScrollBehavior = daySlider.style.scrollBehavior;
      daySlider.style.scrollBehavior = 'auto';
      daySlider.scrollLeft = targetLeft;
      daySlider.style.scrollBehavior = previousScrollBehavior;
    }} else {{
      daySlider.scrollTo({{ left: targetLeft, behavior }});
    }}
    window.setTimeout(() => {{ isProgrammaticScroll = false; }}, behavior === 'smooth' ? 260 : 80);
  }});
}}

function setCurrentDay(index, shouldScroll = true, behavior = 'smooth') {{
  const total = dayTitles.length;
  currentDay = Math.max(0, Math.min(index, total - 1));
  pagerIndex.textContent = String(currentDay + 1);
  pagerTitle.textContent = dayTitles[currentDay];
  pagerDots.forEach((dot, dotIndex) => dot.classList.toggle('active', dotIndex === currentDay));
  if (shouldScroll) {{
    scrollToCurrentDay(behavior);
  }}
}}

document.querySelectorAll('.tab').forEach((tab) => {{
  tab.addEventListener('click', () => {{
    document.querySelectorAll('.tab').forEach((item) => item.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach((panel) => panel.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
    if (tab.dataset.tab === 'daily') scrollToCurrentDay('auto');
    if (window.lucide) window.lucide.createIcons();
  }});
}});
document.getElementById('prevDay').addEventListener('click', () => setCurrentDay(currentDay - 1));
document.getElementById('nextDay').addEventListener('click', () => setCurrentDay(currentDay + 1));
pagerDots.forEach((dot) => dot.addEventListener('click', () => setCurrentDay(Number(dot.dataset.slide))));
daySlider.addEventListener('scroll', () => {{
  if (isProgrammaticScroll) return;
  window.clearTimeout(daySlider._snapTimer);
  daySlider._snapTimer = window.setTimeout(() => {{
    const slides = Array.from(daySlider.children);
    const nearest = slides.reduce((best, slide, index) => {{
      const distance = Math.abs((slide.offsetLeft - daySlider.offsetLeft) - daySlider.scrollLeft);
      return distance < best.distance ? {{ index, distance }} : best;
    }}, {{ index: currentDay, distance: Number.POSITIVE_INFINITY }});
    setCurrentDay(nearest.index, false);
  }}, 80);
}});
window.addEventListener('resize', () => setCurrentDay(currentDay, true, 'auto'));

// Auto-jump to today's card only while the trip is in progress. e.g.
// start=2026-07-17 and today=2026-07-21 -> D5. If today is before or after
// the trip, stay on D1 so the itinerary opens from the beginning.
function todayDayIndex() {{
  if (!tripStartDate) return 0;
  const start = new Date(tripStartDate + 'T00:00:00');
  if (isNaN(start)) return 0;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  start.setHours(0, 0, 0, 0);
  const diffDays = Math.round((today - start) / 86400000);
  if (diffDays < 0 || diffDays >= dayTitles.length) return 0;
  return diffDays;
}}
setCurrentDay(todayDayIndex(), false);
if (window.lucide) window.lucide.createIcons();
</script>
</body>
</html>
'''
    path.write_text(html_text, encoding="utf-8")
