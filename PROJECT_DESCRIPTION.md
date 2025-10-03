# Oroto AI - Terminal-Based Automatic Coding Assistant

## Overview & Purpose

**Oroto AI** is an intelligent terminal-based coding assistant designed to help developers with both everyday conversations and complex, long-term project execution. The system operates in two distinct modes:

### Operating Logic

1. **Conversation Mode**
   - Handles quick questions, explanations, and general knowledge queries
   - Provides instant responses without complex task breakdown
   - Perfect for troubleshooting, learning, and casual interaction

2. **Project Mode**
   - Automatically detects when you're requesting file operations or building applications
   - Breaks complex tasks into 3-10 logical steps
   - Asks for permission **once** at the start, then executes all steps automatically
   - Creates version snapshots after each step for rollback capability
   - Prevents hallucinations in long tasks by trimming context intelligently

### Key Features
- **One-time permission system**: No interruptions during execution
- **Automatic task decomposition**: AI analyzes and breaks down complex requests
- **Per-step version control**: Every change is tracked and can be rolled back
- **Security-first design**: All file operations are validated and contained
- **Project persistence**: Save, resume, and manage long-term projects

---

## Project Architecture & File Functions

### Core Application Files

#### 1. **`main.py`** - Application Entry Point
**Purpose**: Main orchestration and execution engine

**Key Components**:
- `AIClient` - Handles communication with OpenRouter API
- `ProjectState` - Manages project persistence and state saving to `.cli_projects/`
- `TaskPlanner` - Analyzes user input to determine conversation vs. project mode
- `StepExecutor` - Executes tasks step-by-step with automatic progression
- Main event loop with command processing

**Interactions**:
- Imports configuration from `config.py`
- Uses command functions from `commands.py`
- Calls helper functions from `thinking_python.py`
- Saves project state to `.cli_projects/` directory
- Creates version snapshots in `.versions/` directory

---

#### 2. **`config.py`** - Configuration Manager
**Purpose**: Centralized configuration loading and validation

**Functions**:
- `get_config()` - Reads configuration from environment variables or `.env` file
- `validate_config()` - Ensures required settings (API key, model) are present

**Configuration Sources** (in priority order):
1. Environment variables (Replit Secrets)
2. `.env` file in project root
3. Default values

**Interactions**:
- Called by `main.py` on startup
- Fails fast if API key is missing

---

#### 3. **`commands.py`** - Safe Command Execution Module
**Purpose**: Provides predefined, secure functions for file operations

**Available Functions**:
- `list_directory(path)` - Lists files and folders with metadata
- `read_file(file_path, max_lines)` - Reads file contents safely
- `write_file(file_path, content)` - Creates or updates files
- `create_folder(folder_path)` - Creates directories
- `get_project_structure(path, max_depth)` - Returns complete project tree
- `search_in_files(search_term, pattern)` - Searches across multiple files
- `execute_safe_command(command_name, **kwargs)` - Dispatcher for all commands

**Security Features**:
- All paths validated against path traversal attacks
- Operations restricted to project directory only
- Detailed error reporting

**Interactions**:
- Imported by `main.py` for file operations
- Can be used by AI during project execution
- All functions return structured JSON results

---

#### 4. **`thinking_python.py`** - Helper Utilities Module
**Purpose**: Advanced helper functions for complex operations

**Key Functions**:
- `break_down_task()` - Decomposes tasks into logical steps
- `validate_file_path()` - Validates paths with security checks
- `create_project_structure()` - Creates complete file/folder hierarchies
- `update_code_section()` - Updates specific code sections only
- `create_version_snapshot()` - Saves project state for rollback
- `validate_project_consistency()` - Checks project structure integrity
- `prevent_hallucination_in_long_tasks()` - Trims context for long operations
- `estimate_task_complexity()` - Analyzes task difficulty
- `sanitize_input()` - Cleans user input for safety

**Interactions**:
- Imported by `main.py` for task management
- Provides utilities for secure file operations
- Handles version control and consistency validation

---

### Configuration Files

#### 5. **`.env`** - Environment Configuration (User-Created)
**Purpose**: Stores API key and model configuration

**Required Variables**:
```
AI_API_KEY=your_api_key_here
MODEL=x-ai/grok-4-fast:free
API_ENDPOINT=https://openrouter.ai/api/v1/chat/completions
```

**Note**: Create this file by copying `.env.example` and adding your actual API key

**Security**: 
- Not committed to version control (in `.gitignore`)
- Read by `config.py` on startup
- Alternative: Use Replit Secrets for cloud deployments

---

### Data Directories

#### 6. **`.cli_projects/`** - Project State Storage
- Stores active and paused project states as JSON files
- Each project has a unique ID: `project_YYYYMMDD_HHMMSS.json`
- Contains: task description, steps, results, progress, and context

#### 7. **`.versions/`** - Version Control Snapshots
- Stores per-step snapshots of project files
- Directory structure: `.versions/<project_id>_step<N>_<timestamp>/`
- Allows rollback to any previous step

---

## System Workflow

```
User Input
    ↓
main.py (TaskPlanner)
    ↓
Analyze: Conversation or Project?
    ↓
    ├─→ Conversation Mode: Direct AI response
    │
    └─→ Project Mode:
            ↓
        Break into steps (thinking_python.py)
            ↓
        Ask permission ONCE
            ↓
        Execute steps automatically (StepExecutor)
            ↓
        For each step:
            ├─→ Execute AI response
            ├─→ Create version snapshot (.versions/)
            ├─→ Save project state (.cli_projects/)
            └─→ Continue to next step
            ↓
        Complete with summary
```

---

## Getting Started

1. **Configure API Key**:
   ```bash
   cp .env.example .env
   # Edit .env and add your OpenRouter API key
   ```

2. **Run the application**:
   ```bash
   python main.py
   ```

3. **Try it out**:
   - Simple question: "What is Python?"
   - Project request: "Create a simple website with HTML, CSS, and JavaScript"

---

## Dependencies

- **httpx**: HTTP client for API communication
- **rich**: Terminal UI library for beautiful CLI experience
- **pathlib**: File path operations
- **json**: Data serialization

Install with:
```bash
pip install httpx rich
```

---

## Security Features

- ✅ Path traversal protection
- ✅ Operations restricted to project directory
- ✅ API key stored securely (not in code)
- ✅ Input sanitization
- ✅ Validation on all file operations

---

## Project Philosophy

**Oroto AI** is built on four principles:

1. **One-time permission** - Ask once, execute smoothly
2. **Targeted updates** - Change only what's requested
3. **Version everything** - Track every step for safety
4. **Clear feedback** - Always show what's happening

This creates a powerful yet safe coding assistant that respects your workflow while automating complex tasks efficiently.
