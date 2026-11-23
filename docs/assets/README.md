# Assets and screenshots

← [Documentation home](../README.md) · Brand rules: [product/brand.md](../product/brand.md)

## Brand files

| File | Use |
|---|---|
| [`brand/nexaro-logo-light.svg`](brand/nexaro-logo-light.svg) | Logo for light backgrounds (navy wordmark) |
| [`brand/nexaro-logo-dark.svg`](brand/nexaro-logo-dark.svg) | Logo for dark backgrounds (light wordmark) |
| [`brand/nexaro-mark.svg`](brand/nexaro-mark.svg) | Monogram only (avatars, favicons, small sizes) |

The wordmark is set in Inter SemiBold (the UI font, bundled under the SIL OFL in
`frontend/fonts/`) and converted to outlines, so it renders identically without the font installed.

## Product screenshots

All screenshots are of the **real application** running in real Chromium, at 1280×800 and 2× scale.
They are reproducible:

```bash
make screenshots    # needs the dev environment and Node ≥ 20; writes docs/assets/screenshots/
```

How they are produced (`tests/frontend/demo_server.py` and `tests/frontend/screenshots.mjs`):

- A temporary database with neutral demo accounts (`admin@example.com`, …). **No personal data.**
- Demo content (an organization, three short documents, two personal agents, four prompts installed from
  the built-in catalogue, three conversations) is created through the **public API**, as a user would.
- No language model runs during the capture. A stand-in for Ollama reports two typical local models
  (`qwen2.5:3b`, `llama3.2:3b`) so model-related screens can render. **No screenshot shows model-generated
  text.** The script fails if the stand-in's placeholder text ever appears on screen.

| File | Screen | Shows |
|---|---|---|
| `dashboard.png` / `dashboard-dark.png` | Panel | Activity, messages per day, recent conversations, admin platform metrics |
| `chat-dark.png` | Chat | Composer, agent selector, model selector (auto / pinned), document retrieval toggle, history |
| `agents.png` | Agentes | Personal agent editor (tools, model) and the user's agents |
| `documents.png` | Documentos | Organization documents for retrieval (BM25 with sources) |
| `prompts.png` | Prompt Library | Versioned prompts installed from the catalogue |
| `model-management.png` | Administración → Modelos | Gateway routes, status, circuit breaker, installed models |
| `operations.png` | Administración → Operaciones | Services, database integrity, resources, latency, backup status |
| `security.png` | Seguridad | Security summary derived from the audit log |

### Screenshot plan: still to capture manually

These require a real model or a real deployment and **must be captured by hand** on a machine running
`make up && make model`:

| # | Screen | Why it can't be automated here | How to capture |
|---|---|---|---|
| 1 | **Chat with a real answer** (streaming, Markdown, code block) | Needs a real Ollama model | Ask the Developer agent a short coding question; capture after the answer completes |
| 2 | **Chat answering from documents with sources** | Needs a real model | Upload a document, enable "Consultar mis documentos", ask about it |
| 3 | **Tutor agent** guiding instead of solving | Needs a real model | Select "Tutor de programación", ask for help with an exercise |
| 4 | **Architecture diagram** | Not a screen | Use the Mermaid diagrams in [architecture/overview.md](../architecture/overview.md), which GitHub renders |

Rules for manual captures: use demo accounts and demo content only, crop out the browser chrome, use a
1280×800 window, save as PNG under 500 KB (`pre-commit` rejects larger files), and never show real
conversations, e-mails, IP addresses or keys.

### Not shown on purpose

Screens for capabilities that do not exist yet (agent runtime, orchestrator, memory, multi-agent teams,
vector search) are intentionally absent. See the [capability matrix](../product/capabilities.md).

## Design reference screenshots

`docs/design/screenshots/` holds the visual-regression captures written by
`BROWSER=1 bash tests/frontend/run.sh`. They use the E2E test double and are for design review, not for
product presentation.
