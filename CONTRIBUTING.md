# Contributing

Co-pilot Facultate is currently a personal project, but issues and small pull requests are welcome.

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Commit style

Use concise, imperative commit messages:

```text
Fix abandoned AI queue requests
Polish chat UX and repository quality
Add factual verification tools
```

Avoid vague messages such as `update`, `fix stuff` or `changes`.

## Pull requests

- Keep changes focused.
- Include tests or a manual verification note.
- Do not commit local documents, ChromaDB data, SQLite databases, secrets or generated build folders.
- Use the product name **Co-pilot Facultate** consistently.
