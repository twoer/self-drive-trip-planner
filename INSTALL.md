# Installation Guide

This guide covers the three common ways to use Self-Drive Trip Planner:

- run it directly from the repository
- install it as a Codex skill
- install it as a local Codex plugin

## Requirements

- Python 3.10+
- `make`
- Codex CLI, only needed for skill or plugin installation
- Optional: a Gaode/Amap Web Service key for accurate mainland China routing

Install Python dependencies:

```bash
make install
```

## Quick Local Demo

Generate a local demo page from `examples/simple-trip.txt`:

```bash
make setup
make demo
open trip-output/trip.html
```

Without a map API key, the demo uses estimated route metrics and records warnings
in `trip-output/manifest.json`.

## Configure Amap

For accurate route distance, duration, tolls, and map paths, create a Web Service
key in the Gaode/Amap console:

https://console.amap.com/dev/key/app

Then put the key in local `.env`:

```bash
AMAP_KEY=your-gaode-web-service-key
```

`GAODE_KEY` is also supported. The `.env` file is ignored by git and excluded
from plugin packages.

## Install As A Codex Skill

Use this when you want the repository copied into your local Codex skills folder:

```bash
make install-skill
```

Then start a new Codex task and ask it to use `$self-drive-trip-planner` with an
itinerary.

## Install As A Codex Plugin

Use this when you want the project to appear as a local plugin in your personal
Codex marketplace:

```bash
make install-plugin
```

This command:

- builds a clean plugin package under `dist/`
- copies it to `~/plugins/self-drive-trip-planner`
- updates `~/.agents/plugins/marketplace.json`
- runs `codex plugin add self-drive-trip-planner@personal`

Start a new Codex task after installing so the skill list refreshes.

Verify the install:

```bash
codex plugin list
```

You should see:

```text
self-drive-trip-planner@personal  installed, enabled
```

## Build A Release Package

Build a zip that can be uploaded to GitHub Releases:

```bash
make package-plugin
make check-plugin-package
```

The zip is written to:

```text
dist/self-drive-trip-planner-plugin.zip
```

## Troubleshooting

If `codex` is not found, install or update Codex CLI first, then rerun:

```bash
make install-plugin
```

If a new Codex task cannot see the skill, check that the plugin is enabled:

```bash
codex plugin list
```

If route data looks estimated, confirm that `.env` contains a real `AMAP_KEY` or
`GAODE_KEY`, then rerun:

```bash
make demo-api
```

If `make demo-api` fails, the key may not be a Web Service key, the quota may be
exhausted, or the map provider may not recognize one of the stop names.
