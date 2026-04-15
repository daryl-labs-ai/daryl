"""agent-mesh dashboard — read-only UI.

Serves a single-page HTML dashboard + a tiny JSON API, both on port 8001
by default. Data is read from the agent-mesh data directory
(`events.jsonl` + `index.sqlite3`). Never writes.
"""
