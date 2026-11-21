import json
from pathlib import Path
from typing import Any
from app.config import settings

class AgentRegistry:
    def __init__(self, catalogue_path: Path | None = None):
        self.path = catalogue_path or settings.catalogue_path
        self._catalogue: dict[str, Any] = {}

    def load(self) -> None:
        if not self.path.exists():
            raise FileNotFoundError(f"Agent catalogue not found: {self.path}")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        agents = data.get("agents")
        if not isinstance(agents, list):
            raise ValueError("Catalogue must contain an agents array")
        self._catalogue = {agent["id"]: agent for agent in agents}

    def list_agents(self) -> list[dict[str, Any]]:
        return list(self._catalogue.values())

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        return self._catalogue.get(agent_id)

registry = AgentRegistry()
