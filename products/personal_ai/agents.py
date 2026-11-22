"""Agentes especializados de NEXARO Personal AI (ADR-0022).

Un agente es un perfil fijo: reglas que se añaden al prompt general, las herramientas que puede
usar y el tope de salida para código. Las herramientas las ejecuta el backend, no el modelo: el
usuario las activa y el backend comprueba que el agente las tiene y que el usuario tiene el
permiso que exigen.
"""

from dataclasses import dataclass
from typing import get_args

from products.personal_ai.prompts import AGENT_RULES, AgentId

# Herramienta → permiso de organización que exige.
TOOL_PERMISSIONS: dict[str, str] = {"documents": "documents:read"}

DOCUMENTS = frozenset({"documents"})


@dataclass(frozen=True)
class Agent:
    id: str
    name: str
    description: str
    tools: frozenset[str]
    # False: las preguntas de código usan el tope general, no el largo (respuestas breves).
    long_code_answers: bool = True

    def public(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tools": sorted(self.tools),
        }


AGENTS: dict[str, Agent] = {
    agent.id: agent
    for agent in (
        Agent("general", "Asistente general", "Preguntas y tareas generales.", DOCUMENTS),
        Agent(
            "developer",
            "Desarrollador de software",
            "Diseño, escritura, revisión y depuración de código.",
            DOCUMENTS,
        ),
        Agent(
            "security",
            "Analista de ciberseguridad",
            "Riesgos, hardening, logs y vulnerabilidades, con enfoque defensivo.",
            DOCUMENTS,
        ),
        Agent(
            "research",
            "Asistente de investigación",
            "Investigar un tema y estructurar conclusiones citando tus documentos.",
            DOCUMENTS,
            long_code_answers=False,
        ),
        Agent(
            "productivity",
            "Gestor de productividad",
            "Planificar, priorizar y dividir el trabajo en pasos.",
            DOCUMENTS,
            long_code_answers=False,
        ),
        Agent(
            "data",
            "Analista de datos",
            "Análisis de datos, consultas SQL y código de análisis.",
            DOCUMENTS,
        ),
        # Sin documentos: trabaja sobre el ejercicio del estudiante (mínimo privilegio).
        Agent(
            "tutor",
            "Tutor de programación",
            "Te guía con pistas en vez de darte la solución.",
            frozenset(),
            long_code_answers=False,
        ),
    )
}

# El registro, los prompts y el tipo de la API no pueden desincronizarse.
assert set(AGENTS) == set(AGENT_RULES) == set(get_args(AgentId))


def get_agent(agent_id: str) -> Agent:
    return AGENTS[agent_id]


def public_agents() -> list[dict[str, object]]:
    return [agent.public() for agent in AGENTS.values()]
