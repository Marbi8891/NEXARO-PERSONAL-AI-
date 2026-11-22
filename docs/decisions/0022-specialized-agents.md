# ADR-0022: Agentes especializados con herramientas por permiso

- **Estado:** Propuesta (implementada y probada con un modelo falso; pendiente de evaluar la calidad con `qwen2.5:3b`)
- **Fecha:** 2026-11-18

## Contexto

El prompt maestro pide seis agentes: General, Software Developer, Cybersecurity Analyst, Research,
Productivity y Data Analyst. Deben usar herramientas con permisos explícitos y registrar sus acciones.
Ya existía el modo tutor (ADR-0020), que es un perfil de prompt elegido en cada mensaje. El esquema
tiene las tablas `agents` y `agent_runs`, por organización y sin uso. El modelo es un 3B en CPU, sin
GPU: la primera respuesta tarda unos 20 s y las siguientes 1–2 s (medido con `make smoke`).

## Opciones

- A. **Agentes con *tool calling* del modelo.** El modelo decide qué herramienta usar y el backend
  la ejecuta. Un 3B elige mal las herramientas y los argumentos. Cada llamada es otra generación
  completa en CPU. Además, el modelo pasaría a controlar acciones (más superficie de inyección de
  prompts).
- B. **Agentes como perfiles con herramientas declaradas.** Cada agente aporta reglas de prompt, sus
  herramientas y su tope de salida. Las herramientas las activa el usuario y las ejecuta el backend,
  que comprueba que el agente las tiene y que el usuario tiene el permiso que exigen.
- C. **Agentes creados por el usuario** en las tablas `agents` y `agent_runs` (por organización,
  `agents:manage`). Necesita interfaz de gestión, versionado de prompts y evaluación de cada prompt.

## Decisión

B, con el registro en código (`products/personal_ai/agents.py`):

| Agente | Herramientas | Respuestas largas de código |
|---|---|---|
| `general` | `documents` | sí |
| `developer` | `documents` | sí |
| `security` | `documents` | sí |
| `research` | `documents` | no |
| `productivity` | `documents` | no |
| `data` | `documents` | sí |
| `tutor` | ninguna (mínimo privilegio: trabaja sobre el ejercicio) | no |

- **Prompt:** cada agente **añade** sus reglas a `SYSTEM_PROMPT`. Identidad, jerarquía de
  instrucciones, privacidad y confidencialidad (ADR-0019) son las mismas para todos, y el filtro de
  temas internos se aplica antes de elegir agente. Un test comprueba que el registro, los prompts y el
  tipo `AgentId` de la API no se desincronizan.
- **Permisos por herramienta:** `TOOL_PERMISSIONS` asocia cada herramienta a un permiso de
  organización (`documents` → `documents:read`). Hacen falta las dos condiciones: el agente debe
  tenerla (403 si no, sin llegar al modelo ni guardar el turno) y el usuario debe tener el permiso
  en esa organización (la comprobación de siempre).
- **Registro de acciones:** el evento de auditoría `agent.tool` guarda el resultado (`success` o
  `denied`), el usuario, la organización y, en `details`, el agente, la herramienta y el número de
  fuentes o el motivo. Nunca el texto del mensaje ni de los documentos. Además, `messages.agent`
  (migración 7, columna que admite `NULL`) guarda qué agente dio cada respuesta.
- **API:** `GET /api/agents` (sin prompts) y `agent` en el chat web y en `/api/v1/chat`. `mode` sigue
  valiendo cuando no hay `agent`, para no romper Python Learning Dashboard.
- **Interfaz:** el selector «Modo» pasa a ser «Agente» y muestra la descripción. Si el agente no tiene
  la herramienta, el interruptor de documentos se desactiva. La elección se recuerda (también la del
  selector antiguo) y, al reabrir una conversación, se retoma su último agente.

## Razón y trade-offs

B da a cada agente comportamiento y límites reales sin pagar el coste ni el riesgo de A en este
hardware, y reutiliza las comprobaciones de permisos que ya existen.

En contra:
- Hoy solo hay una herramienta (`documents`), así que la diferencia en herramientas solo se ve en el
  tutor. El mecanismo está hecho para las siguientes, por ejemplo tareas en la F28 (solo
  `productivity`).
- La diferencia entre agentes depende de que un 3B respete sus reglas. El backend no puede
  garantizarlo; se mide con `make eval` (VERIFY: faltan casos por agente en `scripts/eval/cases.json`).
- Las tablas `agents` y `agent_runs` siguen sin usarse: se reservan para C, que queda aparcada
  (DECISION REVIEW cuando haga falta crear agentes propios).
- A se reabrirá si se usa un modelo con *tool calling* fiable y medido en este equipo.

## Consecuencias

- Migración 7 (`ALTER TABLE messages ADD COLUMN agent`, en SQLite y PostgreSQL). Solo añade una
  columna: las filas existentes no cambian (`agent` queda `NULL`).
- Tests: `tests/integration/test_agents.py` (registro, prompts, API, presupuesto de salida, auditoría,
  permisos, `/api/v1`) y el E2E del selector. Los tests del modo tutor siguen pasando sin cambios.
