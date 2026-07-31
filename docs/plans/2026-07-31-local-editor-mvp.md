# Local Editor MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a local browser editor that lets a human paste, edit, and generate self-drive trip outputs through the existing route generation engine.

**Architecture:** Add a standard-library Python HTTP server that imports `scripts/route_trip.py` and exposes local-only JSON APIs. The editor UI is a generated static HTML page served by that server; generation still flows through `parse_itinerary()`, `parse_budget_text()`, `enrich()`, `build_budget()`, and `write_outputs()`.

**Tech Stack:** Python 3 standard library `http.server`, existing project Python modules, vanilla HTML/CSS/JavaScript, existing `Makefile`, `unittest`.

---

### Task 1: Add The Local Editor Server

**Files:**
- Create: `scripts/editor_server.py`
- Modify: `Makefile`
- Test: `tests/test_editor_server.py`

**Step 1: Write server tests**

Create tests for:

- `trip_payload_to_text(payload)` converts structured day cards back to D1/D2 text.
- `parse_editor_text(text)` returns route days plus budget text.
- `build_generation_payload(payload, use_api=False)` produces data and manifest-ready output without starting an HTTP server.

Run:

```bash
python3 -m unittest tests/test_editor_server.py
```

Expected: fails because `scripts/editor_server.py` does not exist.

**Step 2: Implement minimal server helpers**

Create `scripts/editor_server.py` with:

- `DEFAULT_HOST = "127.0.0.1"`
- `DEFAULT_PORT = 8765`
- `parse_editor_text(text: str) -> dict`
- `trip_payload_to_text(payload: dict) -> str`
- `generate_from_payload(payload: dict) -> dict`

`generate_from_payload()` should call existing `route_trip` functions directly, not `subprocess`, so API behavior is deterministic and testable.

**Step 3: Add HTTP routes**

Support:

- `GET /` returns the editor page.
- `POST /api/parse` accepts `{"text": "..."}` and returns structured days and budget text.
- `POST /api/generate` accepts structured payload and writes output to `trip-output/editor`.
- `GET /api/manifest` returns `trip-output/editor/manifest.json` when it exists.

Errors should return JSON:

```json
{"ok": false, "error": "human-readable message"}
```

**Step 4: Add Make target**

Add:

```make
editor: install
	$(PYTHON) scripts/editor_server.py
```

Run:

```bash
make editor
```

Expected: prints local URL and waits for requests.

### Task 2: Build The Editor UI

**Files:**
- Modify: `scripts/editor_server.py`
- Test: `tests/test_editor_server.py`

**Step 1: Serve a real tool page**

The first screen should be the editor itself, not a landing page. Use a two-column desktop layout and one-column mobile layout:

- Left panel: raw text input, title, start date, mode.
- Right panel: editable D1/D2 day cards.
- Bottom/right action area: parse, generate, open output.

Keep the UI quiet and utilitarian. No marketing hero.

**Step 2: Follow UI baseline**

Use consistent flex and gap patterns for action groups. Avoid `ml-*`/`mr-*` spacing. Buttons can use clear text labels because the commands are short and unambiguous.

**Step 3: Implement client-side editing**

The page should support:

- Paste raw input.
- Parse into day cards.
- Add day.
- Add route leg to a day.
- Add stay note to a day.
- Delete a day item.
- Generate outputs.
- Show generation result links and warnings.

The client can keep the budget as raw text for MVP. That avoids building a full cost form in the first version while still supporting current natural-language budget parsing.

### Task 3: Keep Packaging And Docs Aligned

**Files:**
- Modify: `README.md`
- Modify: `SKILL.md`
- Modify: `scripts/package_plugin.py` only if new files are not already included by package rules.
- Test: package checks.

**Step 1: Document local editor**

Add a short section:

```bash
make editor
```

Explain that it opens a local browser editor, writes to `trip-output/editor`, and still uses the same generation engine.

**Step 2: Update skill usage**

Add a note to `SKILL.md`:

- Use `make editor` when the user wants a manual visual editing flow.
- Agent generation should still read `manifest.json`.

**Step 3: Verify package contents**

Run:

```bash
make check-plugin-package
```

Expected: package passes and includes `scripts/editor_server.py`.

---

## Plan Review

### Review Result

Approved with scope guardrails.

### Required Adjustments

1. **Keep generation local and bounded.**

   `POST /api/generate` must always write to a repo-local output directory such as `trip-output/editor`. The first version must not accept arbitrary output paths from the browser. This avoids accidental writes outside the project and keeps plugin packaging safer.

2. **Do not make the editor invoke Codex or the skill layer.**

   The editor calls Python helpers directly. The skill remains the Agent-facing workflow, and the editor is the human-facing UI over the same engine.

3. **Use estimate mode by default in the editor.**

   Defaulting to `estimate` makes the local editor work immediately for new users. Users can switch to `auto` or `accurate` after configuring `AMAP_KEY` / `GAODE_KEY`.

4. **Return links, do not launch apps from the server.**

   The editor server should return generated file URLs and manifest JSON. It should not call `open`, start browsers, or perform OS-level actions.

5. **Add HTTP behavior tests.**

   In addition to helper tests, cover bad JSON and missing manifest responses. The important user-facing invariant is: API errors return JSON, not stack traces or HTML.

### Revised MVP Boundaries

In scope:

- Local editor page.
- Paste and parse natural-language input.
- Edit day cards.
- Generate estimate/auto/accurate outputs into `trip-output/editor`.
- View generated output link and manifest warnings.

Out of scope for v1:

- Dragging points on the map.
- Cloud save/share.
- User accounts.
- Full structured fee form.
- Automatic ticket price lookup.
- Writing directly to `docs/` or creating GitHub Pages commits from the editor.

### Task 4: Verify End To End

**Files:**
- `scripts/editor_server.py`
- `tests/test_editor_server.py`
- generated `trip-output/editor/*`

**Step 1: Run all tests**

```bash
make test
```

Expected: all tests pass.

**Step 2: Smoke test server APIs**

Start server on a test port:

```bash
python3 scripts/editor_server.py --port 8766
```

Call:

```bash
curl -s http://127.0.0.1:8766/api/manifest
```

Expected: JSON error if no manifest exists, not an HTML traceback.

**Step 3: Browser smoke test**

Open:

```bash
open http://127.0.0.1:8765
```

Parse `examples/simple-trip.txt`, generate with estimate mode, confirm:

- `trip-output/editor/trip.html` exists.
- `trip-output/editor/manifest.json` exists.
- Page shows generation warnings when using estimate mode.

### Task 5: Commit And Sync

**Files:**
- All modified source, docs, tests.

**Step 1: Commit**

```bash
git add Makefile README.md SKILL.md scripts/editor_server.py tests/test_editor_server.py
git commit -m "feat: add local trip editor"
```

**Step 2: Sync local plugin marketplace**

```bash
make install-plugin
```

Expected: `self-drive-trip-planner@personal` remains enabled and includes the editor script.
