# Server

Infrastructure code for Co-pilot Facultate.

| Folder | Purpose |
| --- | --- |
| `api/` | FastAPI endpoints. |
| `memory/` | Study memory, notebook, progress and persistence. |
| `users/` | Profiles, workspaces and isolation. |
| `queue/` | Request queue, rate limits and concurrency protection. |
| `config/` | Deployment/status helpers. |

Server code should be imported from these packages directly; no business logic lives in the repository root.
