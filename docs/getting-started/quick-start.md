# Quick start

A ten-minute tour after [installation](installation.md). The interface is currently in Spanish;
screen names below are given as *English (Spanish label)*.

← [Installation](installation.md) · Next: [Configuration](configuration.md)

## 1. Check the stack is healthy

```bash
curl -s http://127.0.0.1:8001/api/health
# {"status":"ok","ollama":"connected","model":"ready"}
```

A `503` means Ollama or the model is not available. See [Troubleshooting](troubleshooting.md).

## 2. Chat with a local model

1. Sign in at <http://127.0.0.1:8001> with the administrator you created.
2. Open **Chat**. Type a message and press <kbd>Enter</kbd> (<kbd>Shift</kbd>+<kbd>Enter</kbd> adds
   a new line). Answers stream as they are generated; **Stop (Detener)** cancels.
3. Use the **model selector** to pin a conversation to any model installed in Ollama. A pinned model is
   never silently replaced; if it is missing you get a clear error.

The first answer can take several seconds on CPU while the model loads. It then stays loaded for
30 minutes (`OLLAMA_KEEP_ALIVE`).

## 3. Use a specialised agent

The **agent selector** under the chat box switches between the built-in agents: General, Software
Developer, Cybersecurity Analyst, Research, Productivity, Data Analyst and Programming Tutor.

Under **Agents (Agentes)** you can create your own agent from a base agent: name, instructions and
the subset of tools it may use. Your instructions are added *after* the platform rules, so they
cannot disable the safety guard.

## 4. Ask questions about your documents

1. Open **Documents (Documentos)** and upload a text or PDF file.
2. In Chat, ask a question about it. NEXARO retrieves the most relevant passages (BM25) and the answer
   lists its **sources**.

Documents belong to an organization, so create one first under **Organizations (Organizaciones)**.

## 5. Reuse prompts

**Prompts** holds a versioned prompt library per organization plus a catalogue of 100 ready-made
prompts. Rendering a prompt fills its variables and sends it through the normal chat.

## 6. Administer

Administrators get **Administration (Administración)** for accounts (approval is manual), registration,
models and usage, operations and the audit log, and **Security (Seguridad)** for a summary of failed
logins and denied actions.

## Next steps

- [Configuration](configuration.md)
- [Product capability matrix](../product/capabilities.md): what is and is not implemented
- [User guide](../product/user-guide.md) (Spanish, more detail on each screen)
