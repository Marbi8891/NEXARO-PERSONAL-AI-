"""Estado del sistema para el panel de operaciones (solo administradores; OPERATIONS.md).

Cada sonda es independiente y tolerante: si un dato no está disponible (p. ej. cgroups fuera de
Linux) se devuelve None en lugar de fallar. No incluye secretos, rutas del host ni variables de
entorno; el nombre del modelo sí, porque el endpoint es solo para administradores.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_gateway.usage import UsageStore
from nexaro_api.context import AppContext
from nexaro_core.observability.metrics import RequestMetrics
from products.personal_ai.agents import public_agents

BACKUP_STALE_HOURS = 26  # copia diaria + margen


def _read_int(path: str) -> int | None:
    try:
        raw = Path(path).read_text(encoding="ascii").strip()
    except OSError:
        return None
    return int(raw) if raw.isdigit() else None


def _memory() -> dict[str, Any]:
    used = _read_int("/sys/fs/cgroup/memory.current")
    limit = _read_int("/sys/fs/cgroup/memory.max")  # "max" (sin límite) -> None
    rss = None
    try:
        for line in Path("/proc/self/status").read_text(encoding="ascii").splitlines():
            if line.startswith("VmRSS:"):
                rss = int(line.split()[1]) * 1024
    except (OSError, ValueError):
        pass
    return {
        "container_used_bytes": used,
        "container_limit_bytes": limit,
        "process_rss_bytes": rss,
        "percent": round(used * 100 / limit, 1) if used and limit else None,
    }


def _cpu() -> dict[str, Any]:
    load = os.getloadavg() if hasattr(os, "getloadavg") else None
    quota = None
    try:
        parts = Path("/sys/fs/cgroup/cpu.max").read_text(encoding="ascii").split()
        if len(parts) == 2 and parts[0] != "max":
            quota = round(int(parts[0]) / int(parts[1]), 2)
    except (OSError, ValueError):
        pass
    return {
        "load_1m": round(load[0], 2) if load else None,
        "load_5m": round(load[1], 2) if load else None,
        "cpus_visible": os.cpu_count(),
        "cpu_quota": quota,
    }


def _disk(path: Path) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return {"total_bytes": None, "free_bytes": None, "percent_used": None}
    return {
        "total_bytes": usage.total,
        "free_bytes": usage.free,
        "percent_used": round(usage.used * 100 / usage.total, 1) if usage.total else None,
    }


def _database(ctx: AppContext) -> dict[str, Any]:
    path = ctx.settings.database_path
    try:
        with ctx.database.connect() as db:
            version = db.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
            quick = db.execute("PRAGMA quick_check").fetchone()[0]
            mode = db.execute("PRAGMA journal_mode").fetchone()[0]
    except sqlite3.Error as exc:
        return {"status": "error", "error": type(exc).__name__}
    size = sum(
        p.stat().st_size for p in (path, Path(f"{path}-wal"), Path(f"{path}-shm")) if p.exists()
    )
    return {
        "status": "ok" if quick == "ok" else "degraded",
        "schema_version": version,
        "quick_check": quick,
        "journal_mode": mode,
        "size_bytes": size,
    }


def _backups(ctx: AppContext) -> dict[str, Any]:
    path = ctx.settings.backup_status_path
    if path is None:
        return {"status": "not_configured"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"status": "never"}
    except (OSError, ValueError):
        return {"status": "unreadable"}
    finished = data.get("finished_at")
    age_hours = None
    if isinstance(finished, str):
        try:
            when = datetime.fromisoformat(finished.replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            age_hours = round((datetime.now(timezone.utc) - when).total_seconds() / 3600, 1)
        except ValueError:
            pass
    if not data.get("ok"):
        status = "failed"
    elif age_hours is not None and age_hours > BACKUP_STALE_HOURS:
        status = "stale"
    else:
        status = "ok"
    return {
        "status": status,
        "last_name": data.get("name"),
        "last_reason": data.get("reason"),
        "finished_at": finished,
        "age_hours": age_hours,
        "size_bytes": data.get("size_bytes"),
        "schema_version": data.get("schema_version"),
        "error": data.get("error"),
    }


async def collect(ctx: AppContext, metrics: RequestMetrics) -> dict[str, Any]:
    probe = getattr(ctx.provider, "readiness", None)
    if probe is not None:
        reachable, model_ready = await probe()
    else:
        reachable, model_ready = await ctx.provider.health(), None
    describe = getattr(ctx.provider, "describe", None)
    routes = await describe() if describe is not None else []
    database = _database(ctx)
    try:
        generation = UsageStore(ctx.database).inference(1)
    except sqlite3.Error:
        generation = []
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "backend": {
            "status": "ok",
            "environment": ctx.settings.environment,
            "version": "1.0.0",
        },
        "ollama": {
            "status": "ok" if reachable else "unreachable",
            "model": ctx.personal_ai.model,
            "model_ready": model_ready,
            "routes": [
                {
                    k: r.get(k)
                    for k in ("provider", "model", "healthy", "model_installed", "circuit")
                }
                for r in routes
            ],
        },
        "database": database,
        "agents": [{"id": a["id"], "tools": a["tools"]} for a in public_agents()],
        "system": {
            "cpu": _cpu(),
            "memory": _memory(),
            "disk": _disk(ctx.settings.database_path.parent),
        },
        "requests": metrics.snapshot(),
        "generation_last_24h": generation,
        "backups": _backups(ctx),
    }
