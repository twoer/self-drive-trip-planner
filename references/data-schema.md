# Data Schema

Use this normalized JSON shape between parsing, enrichment, and rendering.

```json
{
  "title": "2026 暑假自驾游",
  "days": [
    {
      "day": "D1",
      "title": "合肥 → 岳阳",
      "notes": [],
      "legs": [
        {
          "from": "合肥",
          "to": "岳阳",
          "distance_km": 600.0,
          "duration_min": 420,
          "toll_cny": 300.0,
          "source": "amap",
          "estimated": false,
          "origin": {"lng": 117.2272, "lat": 31.8206},
          "destination": {"lng": 113.1289, "lat": 29.3571},
          "polyline": [[117.2272, 31.8206], [113.1289, 29.3571]]
        }
      ],
      "distance_km": 600.0,
      "duration_min": 420,
      "toll_cny": 300.0,
      "estimated": false
    }
  ],
  "totals": {
    "distance_km": 600.0,
    "duration_min": 420,
    "toll_cny": 300.0
  },
  "budget": {
    "currency": "CNY",
    "configured": true,
    "total_cny": 1046.0,
    "category_totals": {
      "toll": 300.0,
      "vehicle_energy": 96.0,
      "hotel": 300.0,
      "meal": 100.0,
      "attraction": 250.0
    },
    "items": [
      {
        "category": "vehicle_energy",
        "label": "电车补能",
        "amount_cny": 96.0,
        "detail": "64.0 度 × ¥1/度"
      },
      {
        "category": "attraction",
        "label": "天眼景区",
        "amount_cny": 180.0,
        "detail": "门票免费；摆渡车 3 × ¥50；保险 3 × ¥10",
        "components": [
          {"label": "门票", "unit_price_cny": 0.0, "quantity": 0, "amount_cny": 0.0, "charge": "free"},
          {"label": "摆渡车", "unit_price_cny": 50.0, "quantity": 3, "amount_cny": 150.0, "charge": "per_person"},
          {"label": "保险", "unit_price_cny": 10.0, "quantity": 3, "amount_cny": 30.0, "charge": "per_person"}
        ]
      }
    ],
    "assumptions": {
      "trip_days": 2,
      "distance_km": 600.0,
      "passengers": {
        "adults": 2,
        "children_under_1_2m": 1,
        "children_over_1_2m": 0
      }
    },
    "warnings": []
  }
}
```

Rules:

- `title` must be a non-empty string after trimming whitespace.
- When present, `start_date` must be a valid `YYYY-MM-DD` date string.
- Preserve the user's day labels (`D1`, `D2`, etc.).
- Day labels must start at `D1`; reject labels such as `D0`.
- Each day must include a non-empty string `title`, a `notes` list containing
  only non-empty strings, numeric `distance_km`, numeric `duration_min`, numeric
  `toll_cny`, a boolean `estimated` matching its leg states, and a `legs` list.
- Explicit day labels must be unique after normalization, so `D1` and `Day1`
  in the same input are rejected as duplicates.
- If note-only text appears before the first explicit day label, attach those
  notes to the first explicit day. If route lines appear before explicit labels,
  assign them to the next unused implicit day label without colliding with
  explicit labels.
- Accept day labels with same-line content, such as `D1：合肥 到 岳阳`,
  `Day2 岳阳 到 韶山`, `D3：贵阳市区`, `第1天：合肥 到 岳阳`, or
  `第二天 岳阳 到 韶山`.
- Treat each `A 到 B` line as one driving leg.
- Also accept route connectors such as `到达`, `前往`, `去往`, `至`, `回到`,
  `返回`, `->`, `→`, and spaced dashes such as `合肥 - 岳阳`.
- Treat non-route lines such as `贵阳市区` as day notes. Keep them in `notes`, include them in HTML, and do not count them toward driving totals.
- A generated trip must contain at least one driving leg; note-only inputs are
  rejected with a clean error.
- For a multi-stop line, create adjacent legs: `A 到 B 到 C` becomes `A -> B`, `B -> C`.
- Keep route metrics finite, numeric, and non-negative in JSON. Add units only
  in HTML/SVG labels.
- Leg `from`, `to`, and `source` fields must be non-empty strings. If
  `lookup_error` is present, it must be a non-empty string.
- Non-data-only outputs use one of two map metadata states: a
  `leaflet-playwright-screenshot` source must reference `route-map.png` with
  `fallback=false`, while a `fallback-svg` source must reference
  `route-map.svg` with `fallback=true`. Optional map notes must be non-empty
  strings.
- Coordinates must be finite and within valid longitude/latitude ranges.
  Polylines may be empty when geocoding fails; otherwise they must contain at
  least two points. Complete Amap legs require origin, destination, and at
  least two polyline points.
- Use `estimated: true` when any metric is approximated.
- Keep original place names from the user unless a map API returns a clearly better formatted name and the user has asked for cleanup.
- Keep budget amounts finite, numeric, and non-negative in CNY. If no budget
  inputs are provided, set `budget.configured` to `false` and let the HTML cost
  tab show an activation reminder.
- Budget assumptions must include a positive integer `trip_days` matching the
  largest normalized day number, a distance matching trip totals, and
  non-negative integer counts for all three passenger groups. Optional EV,
  hotel, and meal assumptions must use their documented fields and reproduce
  the corresponding category total.
- Budget items must include non-empty string `category`, non-empty string
  `label`, numeric `amount_cny`, and non-empty string `detail`. Optional
  component rows must include string labels, numeric unit price, numeric
  quantity, numeric amount, and `charge` set to `free` or `per_person`.
- Budget categories are limited to `toll`, `vehicle_energy`, `hotel`, `meal`,
  `attraction`, and `misc`; the same closed set applies to `category_totals`.
- Budget top-level fields follow the documented closed schema. Budget and
  manifest warning lists must be non-empty-string sets in stable order, without
  duplicate entries.
- Item and component amounts must equal unit price times quantity. Free
  components use zero quantity and amount; per-person component quantities
  must equal the total traveler count. Ticket charge counts must match the
  corresponding passenger assumptions.
- User-facing text and warning fields must contain non-whitespace content.
- If a leading or trailing `费用预算：` section is present, parse it separately
  from day notes.
- Hotel nights default to `trip_days - 1`; meal days default to `trip_days`.
- Approximate single amounts such as `酒店每晚约300元`, `酒店每晚300元左右`, and `餐费每天约100元` are accepted as configured amounts.
- Ambiguous hotel, meal, EV price/consumption, ticket, component, or misc-fee ranges such as `300-400 元`, `电价 1.2-1.5 元/度`, or `成人票 100-120 元` are excluded from totals and must be listed in `budget.warnings`. These warnings are also surfaced through `manifest.warnings`.
- Attraction adult ticket prices are multiplied by adult count. Children below 1.2m are free; children at or above 1.2m are half price.
- Component-style fees such as `门票不要钱，摆渡车 50 元一人，保险 10 元一人` are grouped under one attraction item. Per-person components are multiplied by all travelers.
- Detected scenic stops with no configured attraction fee are listed in
  `budget.missing_attractions` with string `name`, string-list
  `matched_names`, string-list `days`, and string `suggestion`. They are
  reminders only and must not change `budget.total_cny`.
