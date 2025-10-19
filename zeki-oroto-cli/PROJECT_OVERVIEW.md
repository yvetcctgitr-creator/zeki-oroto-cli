# Oroto AI CLI — Technical and Functional Overview

This document explains how the system works end-to-end: how it analyzes user input, creates and manages projects, executes commands, launches local development servers, handles files and folders, and uses models and API keys.

## System Overview and Architecture
- Entry point: `main.py` provides the interactive CLI, model selection menu, task planning, step execution, and command handling.
- Process management: `process_manager.py` starts/stops background processes, auto-detects project type, and captures local server addresses from logs.
- Reasoning helpers: `thinking_python.py` contains utilities for breaking down tasks, estimating complexity, creating version snapshots, and validating steps.
- Safe command adapter: `commands.py` exposes safe wrappers for file/dir operations and background process commands.
- Local key store: `key_store.py` saves and retrieves user-provided OpenRouter API keys securely (basic XOR+base64 obfuscation).

The system supports both local Ollama models (`ollama/*`) and remote OpenRouter models (from `models.json`).

## How the AI manages the project process from beginning to end
1. Input and analysis
   - The user enters a request. `TaskPlanner.analyze_task` classifies it as a "conversation" or a "project".
   - For projects, it estimates complexity and produces a step plan with concurrency hints (V6 behavior).
2. Execution orchestration
   - `StepExecutor.execute_complex_task` creates or resumes a project state, sets up workspace, and executes steps.
   - Sub-steps are generated per step and executed in parallel with a bounded concurrency semaphore.
3. Persistence and progress
   - After each step, memory and progress are saved via `ProjectState.save_project` in `.cli_projects/<id>.json`.
   - Version snapshots of changed files are created in `.versions/` to aid rollback.
4. Finalization and auto-launch
   - On completion, the system attempts to auto-launch a dev server (if applicable) and prints the local address.

## How it analyzes user commands and divides them into steps and substeps
- Dynamic planning (V6)
  - `thinking_python.estimate_task_complexity` infers a complexity level (low/medium/high) and recommends step counts.
  - `thinking_python.break_down_task` produces a robust list of steps adapted to the task type.
- Sub-step generation and rules
  - `StepExecutor._generate_substeps` turns each step into actionable sub-steps that the AI must execute.
  - Critical codegen rules are enforced in prompts (e.g., "CREATE FILES WITH CODE at EVERY sub-step").
- Execution and correction
  - `StepExecutor._run_substep` builds a context-rich prompt, runs it, parses results, and applies file/dir operations.
  - A single retry is triggered for detected defects, and results are merged into memory.
- Structured response parsing
  - `ResponseParser` recognizes directives like `CREATE_FILE`, `CREATE_FOLDER`, `CREATE_PROJECT`, plus `RUN_BG`, `STOP_BG`, `RESTART_BG` and synchronous `RUN` commands.

## The command system: How operations such as 'stop', 'abort', and 'resume' work
- Stop/abort active execution
  - Typing `stop` or `abort` requests a graceful cancellation. `StepExecutor.request_stop` sets a stop flag; ongoing sub-steps are cancelled; state is saved with status `stopped`.
  - Background processes are also terminated via `process_manager.stop_all_processes`.
- Resume a saved project
  - `resume <id>` loads `.cli_projects/<id>.json` and restarts `execute_complex_task` from the last saved state.
- Background process utilities
  - `runbg <cmd>` starts an allowed long-running command and captures logs.
  - `ps` lists background processes; `logs <pid> [n]` tails log lines; `kill <pid>` stops a process; `stop-all` stops all.
  - `launch <id>` can auto-detect and run a project’s dev server.

## How the AI runs the project after the project is created and displays the local address
- Auto-detection and launch
  - `process_manager.detect_project_type` inspects the workspace for `package.json`, Python apps (`Flask`, `FastAPI`), Node servers, or `index.html`.
  - It suggests a launch command (e.g., `npm run dev`, `uvicorn main:app --reload`, or `python -m http.server <port>`).
- Static server port resilience
  - For plain static sites, `_find_available_port(8000–8010)` chooses a free port to avoid “address already in use”.
  - `launch_auto` detects immediate exits; for static sites, it retries on an available fallback port.
- Address capture and display
  - The process logs are scanned for URLs using `_URL_RE` and framework-specific patterns.
  - The CLI displays: `✓ Launched dev server (pid …). Access: http://127.0.0.1:...` if detected.

## How the memory, snapshot, and rollback systems work
- Execution memory
  - `StepExecutor` maintains a `self.memory` dict (e.g., `files_created`, `folders_created`, `summaries`, `decisions`) to accumulate context across steps.
  - Memory is persisted in the project state JSON on each step.
- Snapshots for rollback
  - After every step, `thinking_python.create_version_snapshot` stores copies of newly created/modified files under `.versions/<project_id>_stepX_<timestamp>/`.
  - Snapshot metadata includes the project id, step number, timestamp, and the file list.
- Rollback approach
  - Current implementation creates snapshots that can be manually restored (copy files back from `.versions`). A helper to automate restore may be added in future iterations.
- Cancellation persistence
  - On `stop`/`abort`, the system saves partial progress and memory so the project can be resumed safely.

## How model management and user API key verification are performed
- Model sources
  - Local models are fetched from Ollama (`http://localhost:11434/api/tags`) and marked as `type=local`.
  - Remote models are loaded from `models.json` and marked as `type=remote`.
- Selection and menu
  - Press `\` to open the menu: list models or enter your OpenRouter API key (`sk-or-...`). The active model is persisted in `config.json`.
- API key storage and fallback
  - `KeyStore` saves your OpenRouter key encrypted in `key_store.db` and records `use_user_key`.
  - `AIClient` prefers the saved user key; if unavailable, it falls back to the environment `.env`/`AI_API_KEY`.
  - If still missing, the CLI prints a clear diagnostic and tells you how to add the key.
- Local vs remote requests
  - For `ollama/*` models, requests go to the local Ollama server (`/api/chat`).
  - For remote models, requests go to the OpenRouter endpoint with `Authorization: Bearer <key>` headers.

## File and folder management
- The AI’s responses use structured directives:
  - `CREATE_PROJECT: <name>```json ... ````: creates a nested project structure safely with path validation.
  - `CREATE_FILE: <path>```lang ... ````: pre-creates the file and writes content; if the file exists, a diff is computed for transparency.
  - `CREATE_FOLDER: <path>`: ensures directories exist.
- All operations go through safe wrappers (`commands.py`) to prevent path traversal and enforce base-directory constraints.

## Workspace and persistence
- Project state files: `.cli_projects/<id>.json` contain task name, steps, current progress, memory, and sub-step plans.
- Version snapshots: `.versions/` holds per-step file copies for rollback.
- Logs: `.logs/` under the workspace store process stdout/stderr for later inspection.
- Settings: `config.json` saves the active model id/name and `use_user_key` flag.

## Security and safety considerations
- Path validation: file and folder operations validate paths and block traversal attempts.
- Allowed background commands: a limited allowlist prevents unsafe processes from being launched in the background.
- Key handling: the local key store obfuscates keys; remote calls require explicit user keys; environment fallback is supported.

---
By combining dynamic task analysis, parallel sub-step execution, persistent memory, snapshotting, and resilient auto-launch, the CLI can reliably create and run projects while giving you full control to stop, resume, and inspect every step.