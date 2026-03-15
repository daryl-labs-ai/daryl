# Daryl Architecture Overview

High level architecture of the Daryl system.

```
Agents
   │
   ▼
Skills / Sessions
   │
   ▼
RR ─────────── ANS
   │
   ▼
DSM Core
```

- **Agents** interact with Skills and Sessions.
- **RR** provides navigation through DSM.
- **ANS** provides analysis and insights.
- **DSM Core** is the deterministic append-only storage layer.
