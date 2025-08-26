# VS Code Bridge (Local)

Exposes minimal HTTP endpoints so the operator can:
- Save all files
- Read diagnostics (errors/warnings) for the active workspace

**Endpoints** (default `http://127.0.0.1:48100`):
- `POST /saveAll` → saves all
- `GET /diagnostics` → returns `{ uri, diagnostics[] }` per open doc

## Dev
- `npm install`
- `npm run compile`
- Press F5 to run the extension host
