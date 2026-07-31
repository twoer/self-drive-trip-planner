#!/usr/bin/env python3
"""Generate dense random demo trips for UI and output-contract testing."""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

ROUTES = [
    ("华东华南海岸长线", ["合肥", "南京", "扬州", "常州", "无锡", "苏州", "上海", "嘉兴", "杭州", "绍兴", "宁波", "台州", "温州", "福州", "泉州", "厦门", "漳州", "汕头", "深圳", "广州", "珠海", "阳江", "湛江", "北海", "南宁", "桂林", "长沙", "武汉", "合肥"]),
    ("川渝滇黔大环线", ["成都", "德阳", "绵阳", "广元", "汉中", "安康", "重庆", "遵义", "贵阳", "安顺", "兴义", "百色", "南宁", "柳州", "桂林", "怀化", "凤凰古城", "张家界", "常德", "岳阳", "武汉", "宜昌", "恩施", "重庆", "泸州", "宜宾", "乐山", "眉山", "成都"]),
    ("西北丝路青甘线", ["西安", "宝鸡", "天水", "兰州", "西宁", "青海湖", "茶卡盐湖", "德令哈", "大柴旦", "敦煌", "嘉峪关", "张掖", "武威", "中卫", "银川", "榆林", "延安", "临汾", "运城", "洛阳", "郑州", "开封", "商丘", "徐州", "宿州", "合肥"]),
    ("华北山东海岸线", ["北京", "天津", "唐山", "秦皇岛", "锦州", "沈阳", "本溪", "丹东", "大连", "营口", "盘锦", "葫芦岛", "秦皇岛", "天津", "沧州", "德州", "济南", "泰安", "曲阜", "临沂", "日照", "青岛", "威海", "烟台", "潍坊", "淄博", "济南", "石家庄", "北京"]),
    ("云南广西山水线", ["昆明", "玉溪", "普洱", "景洪", "普洱", "大理", "丽江", "香格里拉", "丽江", "攀枝花", "西昌", "昭通", "毕节", "贵阳", "安顺", "兴义", "百色", "南宁", "崇左", "防城港", "北海", "钦州", "南宁", "柳州", "桂林", "贺州", "梧州", "广州"]),
    ("皖赣闽浙山海线", ["合肥", "安庆", "九江", "南昌", "鹰潭", "上饶", "武夷山", "南平", "福州", "莆田", "泉州", "厦门", "龙岩", "赣州", "吉安", "宜春", "萍乡", "长沙", "岳阳", "武汉", "黄石", "九江", "景德镇", "黄山", "宣城", "芜湖", "合肥"]),
    ("中原古都城市线", ["郑州", "开封", "商丘", "徐州", "宿州", "蚌埠", "合肥", "六安", "信阳", "武汉", "襄阳", "十堰", "安康", "西安", "渭南", "运城", "临汾", "晋城", "焦作", "洛阳", "郑州", "许昌", "漯河", "驻马店", "信阳", "合肥"]),
    ("江南亲子城市线", ["上海", "苏州", "无锡", "常州", "镇江", "南京", "马鞍山", "芜湖", "宣城", "湖州", "杭州", "绍兴", "宁波", "舟山", "宁波", "台州", "温州", "丽水", "金华", "衢州", "上饶", "黄山", "池州", "铜陵", "合肥"]),
]

REST_NOTES = ["市区夜游", "老街慢逛", "博物馆半日", "酒店休整补给", "湖边散步", "亲子轻松游"]


def unique_count(stops: list[str]) -> int:
    return len(dict.fromkeys(stops))


def day_counts(count: int, min_days: int, max_days: int) -> list[int]:
    if count <= 1:
        return [min_days]
    if count == 20 and min_days <= 3 and max_days >= 30:
        return [3, 4, 5, 6, 7, 8, 10, 11, 12, 14, 15, 17, 18, 19, 20, 22, 24, 26, 28, 30]
    return [round(min_days + index * (max_days - min_days) / max(1, count - 1)) for index in range(count)]


def build_itinerary(days: int, rng: random.Random) -> tuple[str, int, str]:
    route_name, full_route = rng.choice(ROUTES)
    target_stops = min(len(full_route), max(days, days + rng.choice([0, 1, 2])))
    start = rng.randint(0, max(0, len(full_route) - target_stops))
    stops = full_route[start:start + target_stops]
    cleaned: list[str] = []
    for stop in stops:
        if not cleaned or cleaned[-1] != stop:
            cleaned.append(stop)
    stops = cleaned

    lines: list[str] = []
    leg_index = 0
    rest_budget = max(0, days - (len(stops) - 1))
    for day in range(1, days + 1):
        lines.append(f"D{day}")
        remaining_days = days - day + 1
        remaining_legs = len(stops) - 1 - leg_index
        if remaining_legs <= 0:
            lines.append(f"{stops[-1]}{rng.choice(REST_NOTES)}")
        elif rest_budget > 0 and day not in (1, days) and rng.random() < 0.12:
            lines.append(f"{stops[leg_index]}{rng.choice(REST_NOTES)}")
            rest_budget -= 1
        else:
            legs_today = min(2, max(1, remaining_legs - remaining_days + 1)) if remaining_legs > remaining_days else 1
            for _ in range(legs_today):
                if leg_index >= len(stops) - 1:
                    break
                lines.append(f"{stops[leg_index]} 到 {stops[leg_index + 1]}")
                leg_index += 1
        lines.append("")

    while leg_index < len(stops) - 1:
        lines.insert(len(lines) - 1, f"{stops[leg_index]} 到 {stops[leg_index + 1]}")
        leg_index += 1

    return "\n".join(lines).strip() + "\n", unique_count(stops), route_name


def write_index(base: Path, results: list[dict[str, Any]]) -> None:
    cards = []
    for item in results:
        manifest = item["manifest"]
        totals = manifest.get("totals") or {}
        counts = manifest.get("counts") or {}
        warnings = manifest.get("warnings") or []
        rel_html = f"outputs/trip-{item['idx']:02d}/trip.html"
        rel_input = f"inputs/trip-{item['idx']:02d}.txt"
        rel_manifest = f"outputs/trip-{item['idx']:02d}/manifest.json"
        status = "ok" if item["returncode"] == 0 else "failed"
        warn_class = "ok" if not warnings else "warn"
        warn_text = "no warning" if not warnings else f"{len(warnings)} warning"
        cards.append(
            f"<article class='card'><div class='top'><span class='badge'>{status}</span>"
            f"<span class='{warn_class}'>{warn_text}</span></div><h2>{item['title']}</h2>"
            f"<p>{counts.get('days', item['days'])} 天 · {item['unique_cities']} 城 · "
            f"{counts.get('legs', 0)} 段驾驶 · {manifest.get('data_source', 'unknown')}</p>"
            f"<p>{totals.get('distance_km', 0)} km · {totals.get('duration_min', 0)} min · "
            f"¥{totals.get('toll_cny', 0)}</p><nav><a href='{rel_html}'>打开网页</a>"
            f"<a href='{rel_input}'>输入</a><a href='{rel_manifest}'>manifest</a></nav></article>"
        )
    html = (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Self-Drive Trip Planner Batch Demo</title><style>"
        "body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f6f7f9;color:#172033}"
        "main{max-width:1120px;margin:0 auto;padding:32px 18px 56px}h1{margin:0 0 8px;font-size:28px;letter-spacing:0}"
        "p{margin:0;color:#5c667a;line-height:1.55}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:14px;margin-top:20px}"
        ".card{background:#fff;border:1px solid #e5e9f0;border-radius:8px;padding:16px;box-shadow:0 8px 22px rgba(18,28,45,.05)}"
        ".top{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}"
        ".badge,.ok,.warn{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:4px 8px;font-size:12px;font-weight:700}"
        ".badge{background:#eef4ff;color:#2458a6}.ok{background:#edf8f1;color:#227046}.warn{background:#fff5e7;color:#9a5a14}"
        "h2{margin:0 0 8px;font-size:17px;line-height:1.35;letter-spacing:0}nav{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-top:14px}"
        "a{display:inline-flex;align-items:center;justify-content:center;min-height:34px;padding:0 10px;border-radius:6px;background:#172033;color:#fff;text-decoration:none;font-size:13px}"
        "a+a{background:#edf1f7;color:#273246}</style></head><body><main>"
        "<h1>Self-Drive Trip Planner Batch Demo</h1><p>Dense generated trips for UI and output-contract testing.</p>"
        f"<section class='grid'>{''.join(cards)}</section></main></body></html>"
    )
    (base / "index.html").write_text(html, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate dense random demo trips.")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--min-days", type=int, default=3)
    parser.add_argument("--max-days", type=int, default=30)
    parser.add_argument("--out", default="trip-output/random-demo")
    parser.add_argument("--mode", choices=("auto", "estimate", "accurate"), default="auto")
    parser.add_argument("--seed", type=int, default=20260731)
    parser.add_argument("--with-png", action="store_true", help="Allow Playwright PNG screenshots. Slower.")
    args = parser.parse_args()

    base = ROOT / args.out
    inputs_dir = base / "inputs"
    outputs_dir = base / "outputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)
    env = os.environ.copy()
    if not args.with_png:
        env["SDTP_NO_PLAYWRIGHT"] = "1"

    results: list[dict[str, Any]] = []
    for idx, days in enumerate(day_counts(args.count, args.min_days, args.max_days), start=1):
        itinerary, city_count, route_name = build_itinerary(days, rng)
        title = f"批量样例 {idx:02d} · {days}天 · {city_count}城 · {route_name}"
        input_path = inputs_dir / f"trip-{idx:02d}.txt"
        output_dir = outputs_dir / f"trip-{idx:02d}"
        input_path.write_text(itinerary, encoding="utf-8")
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "route_trip.py"),
            str(input_path),
            "--out",
            str(output_dir),
            "--title",
            title,
            "--start-date",
            (date(2026, 8, 1) + timedelta(days=idx - 1)).isoformat(),
            "--mode",
            args.mode,
        ]
        result = subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True)
        manifest_path = output_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        results.append({
            "idx": idx,
            "title": title,
            "days": days,
            "unique_cities": city_count,
            "returncode": result.returncode,
            "input": str(input_path.relative_to(base)),
            "output": str(output_dir.relative_to(base)),
            "manifest": manifest,
            "stderr": result.stderr,
        })

    (base / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    write_index(base, results)
    print(f"Wrote: {base}")
    print(f"Open: {base / 'index.html'}")
    failed = sum(1 for item in results if item["returncode"] != 0)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
