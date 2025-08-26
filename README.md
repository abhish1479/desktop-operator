# Desktop Operator – AI Agent (Windows-first) 🖥️🤖

A production-ready **starter** for a local desktop AI agent that can:
- Control apps (open windows, click menus, type, copy/paste) via Accessibility / UI Automation
- Run terminal commands (PowerShell/Bash), install packages (winget/choco/brew/apt)
- Manipulate files/folders directly (no flaky UI)
- Automate browsers (Playwright) for web/RPA tasks and AI tools (Runway, Photoroom, Claude, ChatGPT web) when APIs aren’t available
- Integrate with IDEs (VS Code bridge extension) to save/run/get diagnostics
- Execute **skills** (Shopify bulk upload, organize folders, etc.)
- Orchestrate with an LLM (tool-calling), with guardrails and budgets

> **Note**: This is a strong, extensible foundation. Hardening, policy, and enterprise packaging (code signing, MSI, MDM) are left to you.

## Quick Start (Windows recommended)

1. **Install prerequisites**
   - Python 3.11+
   - Node.js 18+ (for VS Code extension build; optional)
   - PowerShell 7+ (`pwsh`)
   - Git
   - VS Code
   - Playwright browsers: `python -m pip install playwright && python -m playwright install`

2. **Setup Python env**
   ```bash
   cd desktop-operator
   python -m venv .venv
   .venv\Scripts\activate   # on Windows
   pip install -r requirements.txt
   ```

3. **Environment**
   - Copy `.env.example` to `.env` and fill keys if using OpenAI/Anthropic/Shopify, etc.

4. **Run the orchestrator API**
   ```bash
   uvicorn apps.orchestrator.main:app --reload --host 127.0.0.1 --port 8000
   ```

5. **(Optional) Install the VS Code extension**
   - Open `vscode-extension` in VS Code
   - `npm install && npm run compile`
   - Press **F5** to run the extension in a new Extension Host window
   - The extension exposes `http://127.0.0.1:48100` for commands:
     - `POST /saveAll`
     - `GET  /diagnostics`

6. **Smoke test**
   ```bash
   # Organize a folder (dry run)
   curl -X POST http://127.0.0.1:8000/skills/files.organize/run ^
     -H "Content-Type: application/json" ^
     -d "{\"root\": \"C:\\Users\\you\\Downloads\", \"rules\": [{\"when_ext\":[\".jpg\", \".png\"], \"action\": \"move\", \"to\": \"Pictures\"}], \"dry_run\": true}"
   ```

7. **Run a goal through the LLM loop** (needs `OPENAI_API_KEY` in `.env`)
   ```bash
   curl -X POST http://127.0.0.1:8000/tasks/run ^
     -H "Content-Type: application/json" ^
     -d "{\"goal\": \"Organize my Downloads: move images to Pictures/ and zips to Installers.\"}"
   ```

## Repo Layout
```
apps/
  orchestrator/     # FastAPI + LLM tool-calling + routers
  worker/           # Desktop tools (PowerShell, FS, UI, browser, VS Code bridge client)
skills/
  files.organize/   # Example skill
  shopify.bulk_upload/
config/
  guardrails.yaml   # Command whitelisting/deny-list
vscode-extension/   # Minimal extension exposing save/diagnostics
```

## Safety & Guardrails
- Command whitelist/deny-list via `config/guardrails.yaml`
- Step count + time budget per run
- Dry-run mode default for file operations
- Approval required for risky ops (you can enforce policies in `apps/orchestrator/policy.py`)

## License
MIT – do what you like; no warranty.
# desktop-operator
