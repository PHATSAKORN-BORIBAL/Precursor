# Dashboard (`app/`)

A no-build, dependency-free web UI served by the FastAPI app.

- `index.html`: page skeleton
- `static/style.css`: styling (dark theme, responsive)
- `static/app.js`: polling, canvas charts, incident replay

Design notes

- Plain JavaScript and `<canvas>`; no CDN, no external requests, so it works offline.
- Server-provided text is inserted with `textContent`, never `innerHTML`.
- The live view polls `GET /api/live?since=<seq>` every 500 ms.
- Selecting an incident switches to a replay view with a scrubber that moves a cursor
  over every channel and shows the estimated onset of each.

Status: **prototype**. Checked with a headless jsdom smoke test
(`scripts/dashboard_smoke.js`, canvas stubbed). It has not been reviewed across
browsers or with screen readers.
