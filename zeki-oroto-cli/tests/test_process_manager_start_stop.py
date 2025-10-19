import asyncio
from pathlib import Path
import pytest

from process_manager import launch_auto, list_processes, stop_all_processes


@pytest.mark.asyncio
async def test_start_stop_static_project(tmp_path_factory):
    ws_dir = Path.cwd() / "Workspace" / "test-static"
    ws_dir.mkdir(parents=True, exist_ok=True)
    index = ws_dir / "index.html"
    index.write_text("<!doctype html><title>Test</title>", encoding="utf-8")

    # Launch auto server (should fall back to python -m http.server)
    res = await launch_auto(cwd=str(ws_dir))
    assert res.get("success"), f"launch_auto failed: {res}"
    pid = res.get("pid")
    assert pid, "Background process should have a PID"

    # Verify process listed
    procs = await list_processes()
    assert procs.get("success")
    assert any(p.get("pid") == pid for p in procs.get("processes", [])), "Process not listed"

    # Stop all processes
    stop_res = await stop_all_processes()
    assert stop_res.get("success")
    assert stop_res.get("count", 0) >= 1, "At least one process should be stopped"