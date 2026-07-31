#!/usr/bin/env python3
"""Local browser editor for self-drive trip inputs.

The editor is a human-facing UI over the same deterministic engine used by the
Codex skill. It does not call Codex; it imports route_trip.py directly.
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import route_trip  # noqa: E402


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_OUTPUT_DIR = ROOT / "trip-output" / "editor"
ALLOWED_MODES = {"estimate", "auto", "accurate", "data-only"}


def day_title(day: dict[str, Any]) -> str:
    legs = day.get("legs") or []
    if legs:
        stops = [str(legs[0].get("from") or "")]
        stops.extend(str(leg.get("to") or "") for leg in legs)
        return " → ".join(stop for stop in stops if stop)
    notes = day.get("notes") or []
    return " / ".join(str(note) for note in notes) if notes else str(day.get("day") or "")


def normalize_editor_day(day: dict[str, Any], index: int) -> dict[str, Any]:
    day_label = str(day.get("day") or f"D{index + 1}").strip() or f"D{index + 1}"
    legs = []
    for leg in day.get("legs") or []:
        origin = str(leg.get("from") or "").strip()
        destination = str(leg.get("to") or "").strip()
        if origin or destination:
            legs.append({"from": origin, "to": destination})
    notes = [str(note).strip() for note in (day.get("notes") or []) if str(note).strip()]
    normalized = {"day": day_label, "legs": legs, "notes": notes}
    normalized["title"] = day_title(normalized)
    return normalized


def parse_editor_text(text: str) -> dict[str, Any]:
    itinerary_text, budget_text = route_trip.split_budget_section(text or "")
    days = route_trip.parse_itinerary(itinerary_text)
    return {
        "route_text": itinerary_text.strip(),
        "budget_text": budget_text.strip(),
        "days": [normalize_editor_day(day, index) for index, day in enumerate(days)],
    }


def trip_payload_to_text(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    budget_text = str(payload.get("budget_text") or "").strip()
    if budget_text:
        lines.append(budget_text)
        lines.append("")

    for index, raw_day in enumerate(payload.get("days") or []):
        day = normalize_editor_day(raw_day, index)
        lines.append(day["day"])
        for leg in day["legs"]:
            origin = str(leg.get("from") or "").strip()
            destination = str(leg.get("to") or "").strip()
            if origin and destination:
                lines.append(f"{origin} 到 {destination}")
        for note in day["notes"]:
            lines.append(note)
    return "\n".join(lines).strip() + "\n"


def generation_text(payload: dict[str, Any]) -> str:
    text = str(payload.get("text") or "").strip()
    if text:
        return text + "\n"
    return trip_payload_to_text(payload)


def generate_from_payload(payload: dict[str, Any], out_dir: Path | None = None) -> dict[str, Any]:
    out_dir = out_dir or DEFAULT_OUTPUT_DIR
    mode = str(payload.get("mode") or "estimate")
    if mode not in ALLOWED_MODES:
        raise ValueError(f"Unsupported mode: {mode}")

    text = generation_text(payload)
    itinerary_text, budget_text = route_trip.split_budget_section(text)
    days = route_trip.parse_itinerary(itinerary_text)
    if not days:
        raise ValueError("没有找到行程。请至少输入一行，例如：合肥 到 岳阳")

    natural_budget = route_trip.parse_budget_text(budget_text)
    route_trip.load_dotenv(ROOT / ".env")
    key = route_trip.amap_key()
    if mode == "estimate":
        key = None
    if mode == "accurate" and not key:
        raise ValueError("accurate 模式需要配置 AMAP_KEY 或 GAODE_KEY。")

    use_api = mode in ("auto", "accurate", "data-only") and bool(key)
    data = route_trip.enrich(days, use_api=use_api)
    data["title"] = str(payload.get("title") or "自驾行程")
    start_date = route_trip.parse_start_date(payload.get("start_date"))
    if start_date:
        data["start_date"] = start_date.isoformat()

    vehicle_type = str(natural_budget.get("vehicle_type") or "none")
    ev_kwh_price = natural_budget.get("ev_kwh_price")
    ev_kwh_per_100km = natural_budget.get("ev_kwh_per_100km")
    if ev_kwh_price is not None and vehicle_type == "none":
        vehicle_type = "ev"
    if vehicle_type == "ev" and ev_kwh_price is not None and ev_kwh_per_100km is None:
        ev_kwh_per_100km = 16.0

    data["budget"] = route_trip.build_budget(
        data,
        vehicle_type=vehicle_type,
        ev_kwh_price=ev_kwh_price,
        ev_kwh_per_100km=ev_kwh_per_100km,
        hotel_nightly=natural_budget.get("hotel_nightly"),
        meal_daily=natural_budget.get("meal_daily"),
        attractions=natural_budget.get("attractions") or [],
        misc_fees=natural_budget.get("misc_fees") or [],
        passengers=natural_budget.get("passengers") or {},
    )
    manifest = route_trip.write_outputs(data, out_dir, key, mode=mode, pdf=bool(payload.get("pdf")))
    files = manifest.get("files") or {}
    html_file = files.get("html")
    return {
        "ok": True,
        "out_dir": str(out_dir),
        "manifest": manifest,
        "output_url": f"/output/{html_file}" if html_file else None,
        "manifest_url": "/api/manifest",
    }


def json_bytes(data: dict[str, Any]) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def error_payload(message: str, status: int = 400) -> dict[str, Any]:
    return {
        "status": status,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps({"ok": False, "error": message}, ensure_ascii=False),
    }


def default_text() -> str:
    path = ROOT / "examples" / "simple-trip.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "D1\n合肥 到 岳阳\n"


EDITOR_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>自驾行程编辑器</title>
  <style>
:root { --bg:#F5F7FA; --card:#FFFFFF; --line:#DDE5EE; --text:#1F2D3D; --muted:#6F7D8C; --primary:#2C6BB2; --accent:#D96B3A; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
button, input, textarea, select { font: inherit; }
.app { max-width: 1320px; margin: 0 auto; padding: 18px; display: grid; gap: 14px; }
.topbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.brand { min-width: 0; }
.brand h1 { margin: 0; font-size: 20px; line-height: 1.2; }
.brand p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
.actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.btn { border: 1px solid var(--line); background: #FFFFFF; color: var(--text); border-radius: 8px; padding: 9px 13px; cursor: pointer; font-weight: 700; }
.btn.primary { background: var(--primary); border-color: var(--primary); color: #FFFFFF; }
.btn.danger { color: #B33D2E; }
.grid { display: grid; grid-template-columns: minmax(360px, 0.9fr) minmax(480px, 1.1fr); gap: 14px; align-items: start; }
.panel { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }
.form-row { display: grid; grid-template-columns: 1fr 150px 130px; gap: 8px; margin-bottom: 10px; }
.field { display: grid; gap: 5px; min-width: 0; }
.field span { font-size: 12px; color: var(--muted); font-weight: 700; }
.input, .textarea, .select { width: 100%; border: 1px solid var(--line); border-radius: 8px; background: #FFFFFF; color: var(--text); padding: 9px 10px; outline: none; }
.textarea { min-height: 560px; resize: vertical; line-height: 1.55; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; }
.day-list { display: grid; gap: 10px; }
.day-card { border: 1px solid var(--line); border-radius: 8px; background: #FFFFFF; overflow: hidden; }
.day-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 10px 12px; border-bottom: 1px solid var(--line); background: #FAFBFC; }
.day-title { display: flex; align-items: center; gap: 8px; min-width: 0; }
.day-label { width: 54px; border: 1px solid var(--line); border-radius: 8px; padding: 7px 8px; font-weight: 800; color: var(--primary); }
.day-route { min-width: 0; font-weight: 800; overflow-wrap: anywhere; }
.item-list { display: grid; gap: 8px; padding: 12px; }
.leg-row, .note-row { display: grid; grid-template-columns: 1fr 1fr auto; gap: 8px; align-items: center; }
.note-row { grid-template-columns: 1fr auto; }
.mini-actions { display: flex; align-items: center; gap: 8px; padding: 0 12px 12px; }
.status { min-height: 22px; color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
.status.error { color: #B33D2E; }
.links { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 8px; }
.links a { color: var(--primary); font-weight: 800; text-decoration: none; }
.warnings { margin-top: 8px; display: grid; gap: 6px; }
.warning { border: 1px solid #F0D1BF; background: #FFF8F3; color: #9B4B28; border-radius: 8px; padding: 8px 10px; font-size: 12px; }
@media (max-width: 860px) { .grid { grid-template-columns: 1fr; } .form-row { grid-template-columns: 1fr; } .textarea { min-height: 360px; } .leg-row { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <h1>自驾行程编辑器</h1>
        <p>本地运行 · 输出到 trip-output/editor · 复用当前生成引擎</p>
      </div>
      <div class="actions">
        <button class="btn" id="parseBtn" type="button">解析</button>
        <button class="btn primary" id="generateBtn" type="button">生成</button>
      </div>
    </header>
    <main class="grid">
      <section class="panel">
        <div class="form-row">
          <label class="field"><span>标题</span><input class="input" id="titleInput" value="自驾行程"></label>
          <label class="field"><span>出发日期</span><input class="input" id="startDateInput" type="date" value="2026-07-17"></label>
          <label class="field"><span>模式</span><select class="select" id="modeInput"><option value="estimate">estimate</option><option value="auto">auto</option><option value="accurate">accurate</option></select></label>
        </div>
        <textarea class="textarea" id="rawInput"></textarea>
      </section>
      <section class="panel">
        <div class="actions" style="justify-content: space-between; margin-bottom: 10px;">
          <strong>行程卡片</strong>
          <button class="btn" id="addDayBtn" type="button">新增一天</button>
        </div>
        <div class="day-list" id="dayList"></div>
        <div class="status" id="statusBox"></div>
        <div class="links" id="resultLinks"></div>
        <div class="warnings" id="warningList"></div>
      </section>
    </main>
  </div>
  <script>
const defaultText = __DEFAULT_TEXT__;
const rawInput = document.getElementById('rawInput');
const dayList = document.getElementById('dayList');
const statusBox = document.getElementById('statusBox');
const resultLinks = document.getElementById('resultLinks');
const warningList = document.getElementById('warningList');
let state = { budget_text: '', days: [] };
rawInput.value = defaultText;

function setStatus(text, isError = false) {
  statusBox.textContent = text || '';
  statusBox.classList.toggle('error', Boolean(isError));
}

function escapeHtml(value) {
  return String(value || '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}

function renderDays() {
  dayList.innerHTML = '';
  state.days.forEach((day, dayIndex) => {
    const card = document.createElement('div');
    card.className = 'day-card';
    const title = day.legs && day.legs.length ? [day.legs[0].from, ...day.legs.map((leg) => leg.to)].filter(Boolean).join(' → ') : (day.notes || []).join(' / ');
    card.innerHTML = `
      <div class="day-head">
        <div class="day-title">
          <input class="day-label" value="${escapeHtml(day.day || ('D' + (dayIndex + 1)))}" data-day-label="${dayIndex}">
          <div class="day-route">${escapeHtml(title || '空白行程')}</div>
        </div>
        <button class="btn danger" type="button" data-delete-day="${dayIndex}">删除</button>
      </div>
      <div class="item-list">
        ${(day.legs || []).map((leg, legIndex) => `
          <div class="leg-row">
            <input class="input" value="${escapeHtml(leg.from)}" data-leg-from="${dayIndex}:${legIndex}">
            <input class="input" value="${escapeHtml(leg.to)}" data-leg-to="${dayIndex}:${legIndex}">
            <button class="btn danger" type="button" data-delete-leg="${dayIndex}:${legIndex}">删除</button>
          </div>`).join('')}
        ${(day.notes || []).map((note, noteIndex) => `
          <div class="note-row">
            <input class="input" value="${escapeHtml(note)}" data-note="${dayIndex}:${noteIndex}">
            <button class="btn danger" type="button" data-delete-note="${dayIndex}:${noteIndex}">删除</button>
          </div>`).join('')}
      </div>
      <div class="mini-actions">
        <button class="btn" type="button" data-add-leg="${dayIndex}">新增路线</button>
        <button class="btn" type="button" data-add-note="${dayIndex}">新增停留</button>
      </div>`;
    dayList.appendChild(card);
  });
}

function syncFromInputs() {
  document.querySelectorAll('[data-day-label]').forEach((input) => {
    state.days[Number(input.dataset.dayLabel)].day = input.value.trim();
  });
  document.querySelectorAll('[data-leg-from]').forEach((input) => {
    const [dayIndex, legIndex] = input.dataset.legFrom.split(':').map(Number);
    state.days[dayIndex].legs[legIndex].from = input.value.trim();
  });
  document.querySelectorAll('[data-leg-to]').forEach((input) => {
    const [dayIndex, legIndex] = input.dataset.legTo.split(':').map(Number);
    state.days[dayIndex].legs[legIndex].to = input.value.trim();
  });
  document.querySelectorAll('[data-note]').forEach((input) => {
    const [dayIndex, noteIndex] = input.dataset.note.split(':').map(Number);
    state.days[dayIndex].notes[noteIndex] = input.value.trim();
  });
}

dayList.addEventListener('click', (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  syncFromInputs();
  if (target.dataset.deleteDay) state.days.splice(Number(target.dataset.deleteDay), 1);
  if (target.dataset.addLeg) state.days[Number(target.dataset.addLeg)].legs.push({ from: '', to: '' });
  if (target.dataset.addNote) state.days[Number(target.dataset.addNote)].notes.push('');
  if (target.dataset.deleteLeg) {
    const [dayIndex, legIndex] = target.dataset.deleteLeg.split(':').map(Number);
    state.days[dayIndex].legs.splice(legIndex, 1);
  }
  if (target.dataset.deleteNote) {
    const [dayIndex, noteIndex] = target.dataset.deleteNote.split(':').map(Number);
    state.days[dayIndex].notes.splice(noteIndex, 1);
  }
  renderDays();
});

document.getElementById('addDayBtn').addEventListener('click', () => {
  syncFromInputs();
  state.days.push({ day: 'D' + (state.days.length + 1), legs: [], notes: [] });
  renderDays();
});

async function postJson(path, payload) {
  const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  const data = await response.json();
  if (!response.ok || data.ok === false) throw new Error(data.error || '请求失败');
  return data;
}

document.getElementById('parseBtn').addEventListener('click', async () => {
  try {
    const data = await postJson('/api/parse', { text: rawInput.value });
    state = { budget_text: data.budget_text || '', days: data.days || [] };
    renderDays();
    setStatus('已解析 ' + state.days.length + ' 天');
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.getElementById('generateBtn').addEventListener('click', async () => {
  try {
    syncFromInputs();
    resultLinks.innerHTML = '';
    warningList.innerHTML = '';
    const data = await postJson('/api/generate', {
      title: document.getElementById('titleInput').value,
      start_date: document.getElementById('startDateInput').value,
      mode: document.getElementById('modeInput').value,
      budget_text: state.budget_text,
      days: state.days
    });
    const links = [];
    if (data.output_url) links.push(`<a href="${data.output_url}" target="_blank" rel="noopener">打开生成网页</a>`);
    links.push(`<a href="${data.manifest_url}" target="_blank" rel="noopener">查看 manifest</a>`);
    resultLinks.innerHTML = links.join('');
    (data.manifest.warnings || []).forEach((warning) => {
      const item = document.createElement('div');
      item.className = 'warning';
      item.textContent = warning;
      warningList.appendChild(item);
    });
    setStatus('已生成到 ' + data.out_dir);
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.getElementById('parseBtn').click();
  </script>
</body>
</html>
"""


def editor_html() -> bytes:
    html = EDITOR_HTML.replace("__DEFAULT_TEXT__", json.dumps(default_text(), ensure_ascii=False))
    return html.encode("utf-8")


class EditorHandler(BaseHTTPRequestHandler):
    server_version = "TripEditor/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[editor] " + fmt % args + "\n")

    def send_bytes(self, body: bytes, status: int = 200, content_type: str = "application/octet-stream") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data: dict[str, Any], status: int = 200) -> None:
        self.send_bytes(json_bytes(data), status=status, content_type="application/json; charset=utf-8")

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8") if raw else "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("请求 JSON 格式错误。") from exc
        if not isinstance(data, dict):
            raise ValueError("请求 JSON 必须是对象。")
        return data

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_bytes(editor_html(), content_type="text/html; charset=utf-8")
            return
        if parsed.path == "/favicon.ico":
            self.send_bytes(b"", status=204, content_type="image/x-icon")
            return
        if parsed.path == "/api/manifest":
            manifest_path = DEFAULT_OUTPUT_DIR / "manifest.json"
            if not manifest_path.exists():
                self.send_json({"ok": False, "error": "还没有生成 manifest。"}, status=404)
                return
            self.send_bytes(manifest_path.read_bytes(), content_type="application/json; charset=utf-8")
            return
        if parsed.path.startswith("/output/"):
            name = unquote(parsed.path.removeprefix("/output/"))
            file_path = (DEFAULT_OUTPUT_DIR / name).resolve()
            if DEFAULT_OUTPUT_DIR.resolve() not in file_path.parents or not file_path.exists():
                self.send_json({"ok": False, "error": "输出文件不存在。"}, status=404)
                return
            content_type = "text/html; charset=utf-8" if file_path.suffix == ".html" else "application/octet-stream"
            self.send_bytes(file_path.read_bytes(), content_type=content_type)
            return
        self.send_json({"ok": False, "error": "接口不存在。"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self.read_json()
            if parsed.path == "/api/parse":
                result = parse_editor_text(str(payload.get("text") or ""))
                self.send_json({"ok": True, **result})
                return
            if parsed.path == "/api/generate":
                self.send_json(generate_from_payload(payload))
                return
            self.send_json({"ok": False, "error": "接口不存在。"}, status=404)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    httpd = ThreadingHTTPServer((host, port), EditorHandler)
    print(f"Editor: http://{host}:{port}")
    print(f"Output: {DEFAULT_OUTPUT_DIR}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local self-drive trip editor.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    run_server(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
