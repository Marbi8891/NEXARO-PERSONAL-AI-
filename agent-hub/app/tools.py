"""Safe workspace tools for the NEXARO coding agent MVP."""
from __future__ import annotations
import asyncio, os, shlex
from pathlib import Path
from typing import Any
from app.config import settings

DENIED_NAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519", "credentials.json"}
DENIED_PARTS = {".ssh", ".aws", ".azure", ".gnupg", "secrets"}
ALLOWED_COMMANDS = {"python", "python3", "pytest", "pip", "pip3", "uv", "node", "npm", "npx", "git", "ruff", "mypy", "make", "docker", "docker-compose", "go", "cargo", "rustc"}

def _workspace() -> Path:
    root = Path(settings.workspace_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root

def _safe_path(relative: str) -> Path:
    root = _workspace()
    if not relative or Path(relative).is_absolute():
        raise ValueError("Path must be a non-empty relative path inside the workspace")
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Path escapes the authorized workspace")
    parts = candidate.relative_to(root).parts if candidate != root else ()
    if any(part.lower() in DENIED_PARTS for part in parts):
        raise PermissionError("Access to sensitive directories is denied")
    if candidate.name.lower() in DENIED_NAMES or candidate.name.lower().startswith(".env"):
        raise PermissionError("Access to sensitive files is denied")
    return candidate

def list_files(path: str = ".") -> dict[str, Any]:
    target = _safe_path(path)
    if not target.exists():
        raise FileNotFoundError(path)
    if not target.is_dir():
        return {"path": path, "files": [target.relative_to(_workspace()).as_posix()]}
    items = []
    for child in sorted(target.iterdir()):
        try:
            safe = _safe_path(child.relative_to(_workspace()).as_posix())
        except (ValueError, PermissionError):
            continue
        items.append({"name": child.name, "path": safe.relative_to(_workspace()).as_posix(), "type": "directory" if child.is_dir() else "file"})
    return {"path": path, "items": items}

def read_file(path: str) -> dict[str, Any]:
    target = _safe_path(path)
    if not target.is_file(): raise FileNotFoundError(path)
    if target.stat().st_size > settings.max_file_bytes: raise ValueError("File exceeds configured read limit")
    return {"path": path, "content": target.read_text(encoding="utf-8", errors="replace")}

def write_file(path: str, content: str) -> dict[str, Any]:
    target = _safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"success": True, "path": path, "bytes_written": len(content.encode("utf-8"))}

def edit_file(path: str, old_string: str, new_string: str) -> dict[str, Any]:
    target = _safe_path(path)
    if not target.is_file(): raise FileNotFoundError(path)
    current = target.read_text(encoding="utf-8")
    count = current.count(old_string)
    if count != 1: raise ValueError(f"Expected old_string exactly once; found {count}")
    target.write_text(current.replace(old_string, new_string, 1), encoding="utf-8")
    return {"success": True, "path": path}

def search_code(query: str, path: str = ".", file_pattern: str = "*") -> dict[str, Any]:
    base = _safe_path(path)
    candidates = [base] if base.is_file() else base.rglob(file_pattern)
    matches = []
    for file in candidates:
        if not file.is_file(): continue
        try:
            rel = file.relative_to(_workspace()).as_posix()
            _safe_path(rel)
            if file.stat().st_size > settings.max_file_bytes: continue
            lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
        except (OSError, ValueError, PermissionError): continue
        for number, line in enumerate(lines, 1):
            if query.casefold() in line.casefold():
                matches.append({"path": rel, "line": number, "text": line[:500]})
                if len(matches) >= 200: return {"matches": matches, "truncated": True}
    return {"matches": matches, "truncated": False}

def create_directory(path: str) -> dict[str, Any]:
    _safe_path(path).mkdir(parents=True, exist_ok=True)
    return {"success": True, "path": path}

async def run_command(command: str, working_directory: str = ".", timeout: int | None = None) -> dict[str, Any]:
    cwd = _safe_path(working_directory)
    if not cwd.is_dir(): raise ValueError("working_directory must be a directory")
    if any(op in command for op in (";", "&&", "||", "|", ">", "<", "`", "$(", "\\n")):
        raise ValueError("Shell operators are disabled; execute one command at a time")
    args = shlex.split(command)
    if not args: raise ValueError("Command is empty")
    executable = Path(args[0]).name.lower()
    if executable not in ALLOWED_COMMANDS: raise PermissionError(f"Command is not allowlisted: {executable}")
    effective_timeout = min(max(timeout or settings.command_timeout_seconds, 1), settings.command_timeout_seconds)
    proc = await asyncio.create_subprocess_exec(*args, cwd=str(cwd), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env={**os.environ, "PYTHONUNBUFFERED": "1"})
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=effective_timeout)
    except asyncio.TimeoutError:
        proc.kill(); await proc.wait()
        return {"command": command, "exit_code": -1, "stdout": "", "stderr": "Command timed out", "timed_out": True}
    return {"command": command, "exit_code": proc.returncode, "stdout": stdout.decode(errors="replace")[-settings.max_command_output_chars:], "stderr": stderr.decode(errors="replace")[-settings.max_command_output_chars:], "timed_out": False}

TOOL_SCHEMAS = [
{"type":"function","function":{"name":"list_files","description":"List workspace files and directories using relative paths.","parameters":{"type":"object","properties":{"path":{"type":"string","default":"."}},"required":[]}}},
{"type":"function","function":{"name":"read_file","description":"Read a text file inside the workspace.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
{"type":"function","function":{"name":"write_file","description":"Create or replace a text file inside the workspace.","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}}},
{"type":"function","function":{"name":"edit_file","description":"Replace one unique occurrence in a workspace file.","parameters":{"type":"object","properties":{"path":{"type":"string"},"old_string":{"type":"string"},"new_string":{"type":"string"}},"required":["path","old_string","new_string"]}}},
{"type":"function","function":{"name":"search_code","description":"Search text within workspace files.","parameters":{"type":"object","properties":{"query":{"type":"string"},"path":{"type":"string","default":"."},"file_pattern":{"type":"string","default":"*"}},"required":["query"]}}},
{"type":"function","function":{"name":"create_directory","description":"Create a directory in the workspace.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
{"type":"function","function":{"name":"run_command","description":"Execute one allowlisted development command without shell operators.","parameters":{"type":"object","properties":{"command":{"type":"string"},"working_directory":{"type":"string","default":"."},"timeout":{"type":"integer"}},"required":["command"]}}}
]
async def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    functions = {"list_files": list_files, "read_file": read_file, "write_file": write_file, "edit_file": edit_file, "search_code": search_code, "create_directory": create_directory, "run_command": run_command}
    if name not in functions: raise ValueError(f"Unknown tool: {name}")
    result = functions[name](**arguments)
    if asyncio.iscoroutine(result): result = await result
    return result
