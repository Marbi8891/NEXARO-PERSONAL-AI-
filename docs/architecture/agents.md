# Agents

← [Architecture overview](overview.md) · Design records:
[ADR-0020](../decisions/0020-tutor-mode.md) · [ADR-0022](../decisions/0022-specialized-agents.md) ·
[ADR-0024](../decisions/0024-organization-agents.md) · Security model:
[agent-security-model.md](../security/agent-security-model.md)

## What an agent is today

In NEXARO v1.0 an agent is a **profile**: a system-prompt specialisation plus the set of tools it is
allowed to use. It runs inside the normal chat request. It does **not** yet plan, loop or call tools
autonomously. That is the planned *Agent Runtime* (see below).

| Kind | Where | Status |
|---|---|---|
| Built-in agents | `products/personal_ai/agents.py` | Implemented |
| Personal agents | `products/personal_ai/custom_agents.py`, `/api/agents/custom`, screen `#/agents` | Implemented |
| Organization agents | `products/personal_ai/org_agents.py`, `/api/organizations/{id}/agents` | API implemented; no UI yet |

### Built-in agents

| ID | Name (UI label) | Purpose |
|---|---|---|
| `general` | General assistant (*Asistente general*) | General questions and tasks |
| `developer` | Software developer (*Desarrollador de software*) | Code, debugging, reviews |
| `security` | Cybersecurity analyst (*Analista de ciberseguridad*) | Defensive security |
| `research` | Research assistant (*Asistente de investigación*) | Structured research |
| `productivity` | Productivity manager (*Gestor de productividad*) | Planning and organisation |
| `data` | Data analyst (*Analista de datos*) | Data analysis |
| `tutor` | Programming tutor (*Tutor de programación*) | Guides learners instead of giving full solutions |

### Personal agents

Users create agents from a built-in base: name, description, instructions and tools. They can edit,
duplicate, enable and disable them. Agents are isolated per user (tested).

## Safety rules (enforced in code, not in prompts)

1. **Instruction ordering:** user instructions are placed *after* the platform's fixed rules and are
   delimited; a test checks they cannot close their delimiter or override the rules.
2. **Tool permission is a subset:** an agent's tools must be a subset of its base agent's tools,
   checked on the server (`403` otherwise).
3. **Tool use is audited:** each tool use records an `agent.tool` audit event.
4. **Restricted-topics guard** (`products/personal_ai/guard.py`) runs before the model for every agent.

## Tools

| Tool | Status |
|---|---|
| `documents`: retrieve passages from the organization's documents (BM25) with sources | Implemented |
| Tool registry (common contract: name, schema, permission, timeout, audit) | Planned |
| Filesystem, Git, shell, code-execution tools | Planned; a prototype exists outside the monolith (PR #3) and was **not merged** because it lacked authentication |

## Planned evolution

The [roadmap](../../ROADMAP.md) orders the next steps: **Agent Runtime** (an executor with step, time
and token budgets) → **Persistent Task Engine** (the `tasks` table already exists) → **Orchestrator** →
**controlled multi-agent execution** → **Memory**. Target design:
[target-architecture.md](target-architecture.md). A proposed catalogue of 86 agent definitions lives in
[`docs/agents/`](../agents/catalogue.md); it is a design artefact, not shipped functionality.
