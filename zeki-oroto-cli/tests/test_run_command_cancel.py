import asyncio
from pathlib import Path
import pytest

from commands import run_command_async


@pytest.mark.asyncio
async def test_run_command_cancel(tmp_path_factory):
    # Create isolated workspace under current project
    ws_dir = Path.cwd() / "Workspace" / "test-cancel"
    ws_dir.mkdir(parents=True, exist_ok=True)

    # Long-running python command
    command = "python -c \"import time,sys; sys.stdout.write('start\\n'); sys.stdout.flush(); time.sleep(5); sys.stdout.write('end\\n')\""

    task = asyncio.create_task(run_command_async(command, cwd=str(ws_dir)))
    await asyncio.sleep(1.0)

    # Request cancellation
    task.cancel()
    cancelled = False
    try:
        await task
    except asyncio.CancelledError:
        cancelled = True

    assert cancelled, "run_command_async should be cancellable"

    # Log file should be created
    logs_dir = ws_dir / ".logs"
    assert logs_dir.exists(), "Logs directory should exist after command run"
    logs = list(logs_dir.glob("cmd-*.log"))
    assert len(logs) >= 1, "A command log should be written"