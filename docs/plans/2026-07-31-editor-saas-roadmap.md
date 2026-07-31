# Editor And SaaS Roadmap

## Current Shape

- `scripts/route_trip.py` is the deterministic route, budget, map, and output engine.
- `scripts/editor_server.py` exposes a local JSON API and writes to `trip-output/editor`.
- `editor/` contains the Vue 3 + TypeScript + Tailwind editor UI.
- Plugin packages include `editor/dist`, so normal users can run `make editor` without Node.js.

## SaaS Target

The SaaS version should keep the same user workflow:

1. Create a trip draft from natural language or empty day cards.
2. Edit days, route legs, stays, passengers, and cost assumptions.
3. Generate route data, map, budget, HTML, and optional PDF.
4. Share a public read-only trip page or keep it private.

## Recommended Service Boundary

- Frontend: reuse the Vue editor and replace local `/api/*` calls with hosted API calls.
- Backend API: wrap the route engine behind authenticated endpoints.
- Storage: persist trip drafts, generated manifests, route cache, and shared-page settings.
- Jobs: run Amap route enrichment, map screenshots, and PDF export asynchronously.
- Price data: cache official or user-confirmed attraction prices with source URLs and checked dates.

## First Hosted Milestone

- Email or phone login.
- Trip CRUD.
- Share token for read-only pages.
- Manual price input plus missing-price warnings.
- Amap key stored on the server, not in the browser.
