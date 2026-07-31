# Plugin Submission Notes

Use this file as the copy/paste source when preparing an external plugin or marketplace submission.

## Identity

- Name: Self-Drive Trip Planner
- Plugin ID: `self-drive-trip-planner`
- Version: `0.3.0`
- Developer: twoer
- Category: Productivity
- Repository: https://github.com/twoer/self-drive-trip-planner
- Website: https://twoer.github.io/self-drive-trip-planner/
- Privacy Policy: https://twoer.github.io/self-drive-trip-planner/privacy.html
- Terms of Use: https://twoer.github.io/self-drive-trip-planner/terms.html
- License: MIT

## Short Description

Generate verifiable Chinese road-trip JSON, HTML, route maps, and manifests.

## Long Description

Self-Drive Trip Planner turns compact D1/D2 Chinese road-trip text into normalized JSON, a standalone mobile-friendly itinerary page, an interactive route map, optional PNG/SVG route images, and a machine-readable manifest. It can use Gaode/Amap route data when `AMAP_KEY` or `GAODE_KEY` is configured, or clearly marked estimates for no-key previews.

## Starter Prompts

- Use my D1/D2 road-trip text to generate JSON, HTML, map, and manifest.
- Generate a self-drive trip with EV charging, hotel, meal, and attraction budget.
- Export the generated self-drive itinerary as a PDF.
- Create an accurate Amap-backed self-drive itinerary from this route.

## Data And Privacy

- The tool runs locally and writes outputs to local folders such as `trip-output/`.
- API keys are read from local environment variables or `.env`.
- `.env` is ignored by git and excluded from generated plugin packages.
- When a map key is configured, stop names and coordinates are sent to Gaode/Amap Web Service for geocoding and driving route calculation.
- Without a key, the tool can generate clearly marked estimated previews.

## External Services

- Optional: Gaode/Amap Web Service for geocoding and driving routes.
- Optional: public map tiles loaded by the generated HTML map in the user's browser.
- Optional: Playwright for local PNG screenshots.

## Limitations

- Route distance, duration, tolls, road conditions, and map positions must be verified before booking, departure, or navigation.
- Toll values depend on map provider response quality and can change.
- Estimated mode is for preview only.
- Mainland China routing is the primary target.

## Screenshots

- `assets/screenshot-desktop.png`
- `assets/screenshot-mobile.png`

## Release Asset

Download the plugin package:

https://github.com/twoer/self-drive-trip-planner/releases/download/v0.3.0/self-drive-trip-planner-plugin.zip

## Pre-Submission Checklist

- `python3 -m unittest discover -s tests`
- `make package-plugin`
- `make check-plugin-package`
- `make validate-plugin` when the local Codex plugin validator is available
- Confirm no secrets are committed:
  `rg -n "AMAP_KEY=.*[0-9A-Za-z]{16}|GAODE_KEY=.*[0-9A-Za-z]{16}" . -g '!dist/**' -g '!trip-output/**'`
- Confirm GitHub Pages demo builds successfully.
- Confirm GitHub Release asset exists for the submitted version.
