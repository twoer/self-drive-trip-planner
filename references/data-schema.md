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
      "toll_cny": 300.0
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
      }
    ],
    "assumptions": {
      "trip_days": 2,
      "distance_km": 600.0
    },
    "warnings": []
  }
}
```

Rules:

- Preserve the user's day labels (`D1`, `D2`, etc.).
- Treat each `A 到 B` line as one driving leg.
- Treat non-route lines such as `贵阳市区` as day notes. Keep them in `notes`, include them in HTML, and do not count them toward driving totals.
- For a multi-stop line, create adjacent legs: `A 到 B 到 C` becomes `A -> B`, `B -> C`.
- Keep route metrics numeric in JSON. Add units only in HTML/SVG labels.
- Use `estimated: true` when any metric is approximated.
- Keep original place names from the user unless a map API returns a clearly better formatted name and the user has asked for cleanup.
- Keep budget amounts numeric in CNY. If no budget inputs are provided, set `budget.configured` to `false` and let the HTML cost tab show an activation reminder.
