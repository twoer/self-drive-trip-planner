# UI Generation Baseline

Use these rules when generating the standalone itinerary HTML.

- Use `flex` or `inline-flex` with centered alignment and a consistent gap for icon-and-text pairs.
- Do not use left or right margins to separate icons from text.
- Give icons explicit width and height, and prevent shrinking.
- Use one consistent gap token for each tab group, toolbar, action group, or compact control cluster.
- Prefer reusable utilities such as `.ui-icon-text` and `.ui-action-group` in generated standalone HTML.
- Keep cards compact, readable, and mobile-first. Use stable dimensions and responsive constraints so labels and dynamic values do not shift layout.
- Do not place detailed segment labels directly on the map when the static map would become cluttered. Keep detailed distance, duration, and toll data in the HTML cards and summary panel.
