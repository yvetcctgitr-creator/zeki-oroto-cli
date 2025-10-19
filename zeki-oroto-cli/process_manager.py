"""
Background Process Manager for Oroto AI CLI
- Start/Stop/Restart processes
- Auto-detect project type and launch dev server
- Capture logs and parse local addresses
"""

import asyncio
import os
import re
import json
import uuid
from datetime import datetime
from pathlib import Path
from asyncio.subprocess import PIPE
from typing import Dict, Optional, List

_REGISTRY: Dict[str, Dict] = {}
_LAST_PID: Optional[str] = None

_URL_RE = re.compile(r"(https?://[\w\-\[\]\.:]+(?:/\S*)?)", re.IGNORECASE)
_ALLOWED_PREFIXES = [
    "npm", "pnpm", "yarn", "npx", "pytest", "pip", "python",
    "node", "serve", "http-server", "uvicorn"
]


# Dynamically find an available local port for static servers
def _find_available_port(start: int = 8000, end: int = 8010) -> int:
    try:
        import socket
        for p in range(start, end + 1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind(("127.0.0.1", p))
                except OSError:
                    continue
                try:
                    s.listen(1)
                except Exception:
                    pass
                return p
    except Exception:
        pass
    return start


def _is_allowed(command: str) -> bool:
    command = (command or "").strip().lower()
    if not command:
        return False
    first = command.split()[0]
    return any(first == p or first.startswith(p) for p in _ALLOWED_PREFIXES)


def _detect_package_manager(cwd: Path) -> str:
    if (cwd / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (cwd / "yarn.lock").exists():
        return "yarn"
    return "npm"


def detect_project_type(cwd: Optional[str] = None) -> Dict:
    """Detect project type and suggest launch command and patterns."""
    root = Path(cwd).resolve() if cwd else Path.cwd().resolve()
    info = {
        "type": None,
        "command": None,
        "patterns": [
            r"Local:\s*(https?://[^\s]+)",
            r"Network:\s*(https?://[^\s]+)",
            r"running at\s*(https?://[^\s]+)",
            r"on\s*(http://[^\s]+)",
            r"port\s*(\d{2,5})"
        ],
        "addresses": []
    }

    # Node/React/Vite/Next
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        scripts = (data.get("scripts") or {})
        pm = _detect_package_manager(root)
        if "dev" in scripts:
            info.update({"type": "node-dev", "command": f"{pm} run dev"})
            return info
        if "start" in scripts:
            info.update({"type": "node-start", "command": f"{pm} start"})
            return info
        deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
        if "vite" in deps:
            info.update({"type": "react-vite", "command": f"{pm} run dev"})
            return info
        if "next" in deps:
            info.update({"type": "nextjs", "command": f"{pm} run dev"})
            return info
        if "react-scripts" in deps:
            info.update({"type": "cra", "command": f"{pm} start"})
            return info
        # Fallback to common script names
        if "serve" in scripts:
            info.update({"type": "node-serve", "command": f"{pm} run serve"})
            return info

    # Python frameworks
    if (root / "manage.py").exists():
        info.update({"type": "django", "command": "python manage.py runserver"})
        return info
    app_py = root / "app.py"
    main_py = root / "main.py"
    try:
        if app_py.exists():
            text = app_py.read_text(encoding="utf-8", errors="ignore")
            if "Flask" in text:
                info.update({"type": "flask", "command": "python app.py"})
                return info
        if main_py.exists():
            text = main_py.read_text(encoding="utf-8", errors="ignore")
            if "FastAPI" in text or "uvicorn" in text:
                info.update({"type": "fastapi", "command": "uvicorn main:app --reload"})
                return info
    except Exception:
        pass

    # Plain Node server
    if (root / "server.js").exists():
        info.update({"type": "node-server", "command": "node server.js"})
        return info
    if (root / "index.js").exists():
        info.update({"type": "node-index", "command": "node index.js"})
        return info

    # Static site fallback
    if (root / "index.html").exists():
        port = _find_available_port(8000, 8010)
        info.update({"type": "static", "command": f"python -m http.server {port}"})
        return info

    return info


async def _stream_and_log(stream, log_file: Path, buf: List[str], info: Dict):
    try:
        while True:
            chunk = await stream.read(1024)
            if not chunk:
                break
            text = chunk.decode(errors='ignore')
            buf.append(text)
            try:
                with open(log_file, "a", encoding="utf-8", errors="ignore") as f:
                    f.write(text)
            except Exception:
                pass
            # Parse addresses
            for m in _URL_RE.finditer(text):
                url = m.group(1)
                if url and url not in info["addresses"]:
                    info["addresses"].append(url)
    except Exception:
        # Swallow stream errors
        pass


async def start_process(command: str, cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None, name: Optional[str] = None, project_id: Optional[str] = None) -> Dict:
    """Start a long-running process and capture logs in background."""
    result = {
        "success": False,
        "pid": None,
        "command": command,
        "cwd": str(Path(cwd).resolve()) if cwd else str(Path.cwd().resolve()),
        "log_path": None,
        "error": None,
        "started_at": datetime.now().isoformat(),
        "addresses": [],
    }

    try:
        if not _is_allowed(command):
            result["error"] = "Command not allowed for background execution"
            return result
        workdir = Path(result["cwd"])  # validated above
        if not workdir.exists() or not workdir.is_dir():
            result["error"] = f"Invalid cwd: {workdir}"
            return result
        log_dir = workdir / ".logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.log"

        run_env = os.environ.copy()
        if env:
            for k, v in env.items():
                if isinstance(k, str) and isinstance(v, str):
                    run_env[k] = v

        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(workdir),
            stdout=PIPE,
            stderr=PIPE,
            env=run_env
        )

        pid = uuid.uuid4().hex[:12]
        info = {
            "id": pid,
            "command": command,
            "cwd": str(workdir),
            "proc": proc,
            "log_path": str(log_file),
            "started_at": result["started_at"],
            "ended_at": None,
            "exit_code": None,
            "status": "running",
            "addresses": [],
            "name": name or "process",
            "project_id": project_id,
        }

        stdout_buf: List[str] = []
        stderr_buf: List[str] = []
        t_out = asyncio.create_task(_stream_and_log(proc.stdout, log_file, stdout_buf, info))
        t_err = asyncio.create_task(_stream_and_log(proc.stderr, log_file, stderr_buf, info))

        info["tasks"] = [t_out, t_err]
        _REGISTRY[pid] = info
        global _LAST_PID
        _LAST_PID = pid

        result.update({
            "success": True,
            "pid": pid,
            "log_path": str(log_file),
            "addresses": info["addresses"],
        })
        return result
    except Exception as e:
        result["error"] = str(e)
        return result


async def stop_process(pid: str) -> Dict:
    info = _REGISTRY.get(pid)
    if not info:
        return {"success": False, "error": f"Process not found: {pid}"}
    try:
        proc = info.get("proc")
        if proc and proc.returncode is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        info["ended_at"] = datetime.now().isoformat()
        info["exit_code"] = getattr(proc, "returncode", None)
        info["status"] = "stopped" if info["exit_code"] is None else "exited"
        # Cancel stream tasks
        for t in info.get("tasks", []):
            try:
                t.cancel()
            except Exception:
                pass
        return {"success": True, "pid": pid, "status": info["status"], "exit_code": info["exit_code"]}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def restart_process(pid: str) -> Dict:
    info = _REGISTRY.get(pid)
    if not info:
        return {"success": False, "error": f"Process not found: {pid}"}
    # Stop first
    await stop_process(pid)
    # Start with same params
    return await start_process(info["command"], cwd=info["cwd"], name=info.get("name"), project_id=info.get("project_id"))


async def list_processes() -> Dict:
    items = []
    for pid, info in list(_REGISTRY.items()):
        items.append({
            "pid": pid,
            "command": info.get("command"),
            "cwd": info.get("cwd"),
            "status": info.get("status"),
            "started_at": info.get("started_at"),
            "ended_at": info.get("ended_at"),
            "exit_code": info.get("exit_code"),
            "log_path": info.get("log_path"),
            "addresses": info.get("addresses", []),
        })
    return {"success": True, "processes": items, "last_pid": _LAST_PID}


async def tail_logs(pid: str, n: int = 200) -> Dict:
    info = _REGISTRY.get(pid)
    if not info:
        return {"success": False, "error": f"Process not found: {pid}"}
    log_path = Path(info.get("log_path"))
    if not log_path.exists():
        return {"success": False, "error": f"Log file missing: {log_path}"}
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        tail = lines[-n:] if n and len(lines) > n else lines
        return {"success": True, "pid": pid, "log_path": str(log_path), "lines": tail}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def stop_all_processes() -> Dict:
    errs = []
    total = len(list(_REGISTRY.keys()))
    for pid in list(_REGISTRY.keys()):
        res = await stop_process(pid)
        if not res.get("success"):
            errs.append(res.get("error") or f"Failed to stop {pid}")
    return {"success": not errs, "errors": errs, "count": total - len(errs)}


async def launch_auto(cwd: Optional[str] = None) -> Dict:
    root = Path(cwd).resolve() if cwd else Path.cwd().resolve()
    info = detect_project_type(str(root))
    if not info.get("command"):
        return {"success": False, "error": "Project type not detected; cannot auto-launch"}
    start_res = await start_process(info["command"], cwd=str(root))
    start_res["detected_type"] = info.get("type")
    pid = start_res.get("pid")
    # Briefly check for immediate exit; if so, attempt a static fallback port or report error
    try:
        if pid:
            await asyncio.sleep(0.5)
            pinfo = _REGISTRY.get(pid)
            rc = pinfo.get("proc").returncode if pinfo else None
            if rc is not None:
                # Process exited immediately
                if info.get("type") == "static":
                    port = _find_available_port(8000, 8010)
                    cmd = f"python -m http.server {port}"
                    start_res2 = await start_process(cmd, cwd=str(root))
                    start_res2["detected_type"] = info.get("type")
                    start_res2["fallback_port_used"] = port
                    return start_res2
                else:
                    start_res["success"] = False
                    start_res["error"] = start_res.get("error") or f"Auto-launch exited immediately (code {rc})"
        return start_res
    except Exception:
        return start_res