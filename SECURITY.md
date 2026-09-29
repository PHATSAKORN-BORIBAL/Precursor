# Security Policy

Precursor is an **experimental prototype**. It has not been security-audited and
is not production-ready.

## Reporting a vulnerability

Please open a private security advisory on the GitHub repository (Security tab,
"Report a vulnerability") instead of a public issue. Include steps to reproduce.
Replace this paragraph with a contact address of your choice before publishing.

## Built-in safeguards

- **No secrets in the repo.** The only secret, `PRECURSOR_API_KEY`, is read from the
  environment. `.env` is git-ignored; `.env.example` holds placeholders.
- **Localhost by default.** The server binds to `127.0.0.1`. Starting it on another
  address without an API key prints a warning.
- **API key for writes.** When `PRECURSOR_API_KEY` is set, `POST /api/ingest` and
  `POST /api/sim/inject` require a matching `X-API-Key` header (constant-time compare).
- **Input validation.** Request bodies are validated with Pydantic; non-finite,
  duplicate and out-of-order samples are dropped.
- **Browser hardening.** Responses carry a Content-Security-Policy (`script-src 'self'`),
  `X-Content-Type-Options: nosniff` and `Cache-Control: no-store`. The dashboard
  inserts server text with `textContent` only.
- **Parameterised SQL.** All database access uses bound parameters.
- **Tamper-evident storage.** Incidents are hash-chained (SHA-256).

## Known limits (be honest about these)

- Read endpoints are **unauthenticated**. Anyone who can reach the port can read
  incident data. Put it behind a reverse proxy with authentication if exposed.
- No TLS. Use a reverse proxy for HTTPS; the API key travels in a header.
- The hash chain is **tamper-evident, not tamper-proof**: someone who can rewrite the
  whole SQLite file can rebuild the chain. Publish or anchor the head hash elsewhere
  if you need stronger guarantees.
- No rate limiting, no per-device credentials, no audit log of API calls.
