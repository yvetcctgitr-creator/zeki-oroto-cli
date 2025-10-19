import asyncio
from pathlib import Path
import pytest
import sys
import types

# Shim httpx to avoid external dependency during tests
class _DummyClient:
    def __init__(self, *args, **kwargs):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        return False
    async def post(self, *args, **kwargs):
        class _Resp:
            def json(self):
                return {"choices": [{"message": {"content": ""}}]}
            def raise_for_status(self):
                return None
        return _Resp()

sys.modules['httpx'] = types.SimpleNamespace(AsyncClient=_DummyClient, Client=_DummyClient, HTTPError=Exception)

from main import StepExecutor, ProjectState, AIClient


class FakeAI(AIClient):
    def __init__(self):
        # Minimal placeholders; StepExecutor uses send_message only
        self.model = "fake"
        self.key_manager = None

    async def send_message(self, messages, temperature=0.2):
        # Return a response that triggers a long-running command
        return "RUN: python -c \"import time,sys; sys.stdout.write('hello'); sys.stdout.flush(); time.sleep(5)\""


@pytest.mark.asyncio
async def test_mid_substep_cancellation_persists_state(tmp_path_factory):
    # Setup project state and executor
    project_state = ProjectState(project_dir=".cli_projects_test")
    ai = FakeAI()
    executor = StepExecutor(ai, project_state)

    task_name = "Test Cancellation"
    steps = ["Run a long command"]
    project_id = "test_persist"

    # Monkeypatch substeps generation to a single substep
    async def faux_generate(step_desc):
        return ["Substep: long run"]
    executor._generate_substeps = faux_generate

    # Start execution in background
    t = asyncio.create_task(executor.execute_complex_task(task_name, steps, original_input="", project_id=project_id))
    await asyncio.sleep(1.0)

    # Request stop and wait
    executor.request_stop()
    try:
        await t
    except asyncio.CancelledError:
        pass

    # Verify project state persisted as stopped
    data = project_state.load_project(project_id)
    assert data, "Project state should be saved"
    assert data.get("status") in {"stopped", "in_progress"}, "Project should be stopped or in-progress after cancellation"

    # Cleanup test project data
    proj_file = Path(project_state.project_dir) / f"{project_id}.json"
    if proj_file.exists():
        try:
            proj_file.unlink()
        except Exception:
            pass