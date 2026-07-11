# Server

Infrastructure code for Co-pilot Facultate.

| Folder | Purpose |
| --- | --- |
| `api/` | FastAPI endpoints. |
| `memory/` | Study memory, notebook, progress and persistence. |
| `users/` | Profiles, workspaces and isolation. |
| `queue/` | Request queue, rate limits and concurrency protection. |
| `config/` | Deployment/status helpers. |

Root-level modules such as `api_server.py` and `study_memory.py` are compatibility shims.
