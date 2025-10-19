#!/usr/bin/env python3
"""
Custom AI CLI Tool for Long-Term Projects
A CLI tool designed for step-by-step task execution with built-in task breakdown.
"""

import os
import sys
import json
import re
import httpx
import asyncio
import difflib
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table
from typing import List, Dict, Optional

# Import configuration and commands
from config import get_config, validate_config
from commands import execute_safe_command, execute_safe_command_async
from key_store import KeyStore

# Console setup
console = Console()

# Load configuration
CONFIG = get_config()

# Extract configuration (do not hard-exit if API key is missing)
API_KEY = CONFIG.get("api_key")
API_ENDPOINT = CONFIG.get("api_endpoint")
BASE_DIR = Path(__file__).resolve().parent

# Uzaktaki modeller icin OpenRouter anahtari bilgisi
if not API_KEY:
    console.print("[yellow]Bilgi: Uzaktaki modeller OpenRouter anahtarı gerektirir. \\ tuşuna basarak menüyü açın ve 'Kendi API Anahtarını Gir' seçeneğini kullanın.[/yellow]")

# Model will be selected by user
MODEL = None


def get_ollama_models() -> List[Dict]:
    """Get locally installed Ollama models"""
    try:
        import httpx
        with httpx.Client(timeout=5.0) as client:
            response = client.get("http://localhost:11434/api/tags")
            if response.status_code == 200:
                data = response.json()
                ollama_models = []
                for model in data.get("models", []):
                    # Format size nicely
                    size = model.get('size', 0)
                    if size > 1024**3:  # GB
                        size_str = f"{size / (1024**3):.1f}GB"
                    elif size > 1024**2:  # MB
                        size_str = f"{size / (1024**2):.0f}MB"
                    else:
                        size_str = "Unknown"
                    
                    ollama_models.append({
                        "id": f"ollama/{model['name']}",
                        "name": f"{model['name']} (Local)",
                        "description": f"Local Ollama model - Size: {size_str}",
                        "type": "local"
                    })
                return ollama_models
    except Exception as e:
        # Ollama not running or not available - this is normal
        pass
    return []


def load_models() -> List[Dict]:
    """Load available models from models.json and Ollama"""
    all_models = []
    
    # Load local Ollama models first for better UX (no API key required)
    ollama_models = get_ollama_models()
    all_models.extend(ollama_models)
    
    # Then load remote models from JSON
    try:
        models_file = BASE_DIR / "models.json"
        if models_file.exists():
            with open(models_file, 'r') as f:
                data = json.load(f)
                remote_models = data.get("models", [])
                # Mark as remote models
                for model in remote_models:
                    model["type"] = "remote"
                all_models.extend(remote_models)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load models.json: {e}[/yellow]")
    
    # If no models found, use fallback
    if not all_models:
        all_models = [{"id": "x-ai/grok-4-fast:free", "name": "Grok 4 Fast (Free)", "description": "Default model", "type": "remote"}]
    
    return all_models


def load_user_settings() -> Dict:
    """Load persisted user settings (active model, use_user_key) from config.json"""
    settings_path = BASE_DIR / "config.json"
    if settings_path.exists():
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_user_settings(settings: Dict) -> None:
    """Persist user settings to config.json"""
    settings_path = BASE_DIR / "config.json"
    try:
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        console.print(f"[yellow]Ayarlar kaydedilemedi: {e}[/yellow]")


def select_model(key_store: Optional[KeyStore] = None, current_model: Optional[str] = None) -> str:
    """Model/anahtar menüsü: Modelleri listele veya kullanıcı API anahtarı gir"""
    models = load_models()
    
    console.print("\n[bold #C8A882]═══ Model / API Anahtarı Menüsü ═══[/bold #C8A882]\n")
    console.print("[#C8A882]1.[/#C8A882] Modelleri Listele")
    console.print("[#C8A882]2.[/#C8A882] Kendi OpenRouter API Anahtarını Gir")
    
    top_choice = Prompt.ask("[#C8A882]Seçiminiz[/#C8A882]", default="1")
    
    if top_choice.strip() == "2":
        # Enter user's OpenRouter API key
        if key_store is None:
            try:
                key_store = KeyStore()
            except Exception:
                pass
        api_key_input = Prompt.ask("OpenRouter API Anahtarı (sk-or-...)")
        if not api_key_input or not api_key_input.strip().startswith("sk-or-"):
            console.print("[red]Geçersiz anahtar. OpenRouter anahtarı 'sk-or-' ile başlamalıdır.[/red]")
            return current_model or models[0]["id"]
        try:
            key_store.set_user_key(api_key_input.strip(), provider="openrouter")
            # Persist flag
            settings = load_user_settings()
            settings["use_user_key"] = True
            save_user_settings(settings)
            # Also update process env and module-level API_KEY so remote calls can fall back if needed
            try:
                import os as _os
                global API_KEY
                API_KEY = api_key_input.strip()
                _os.environ["AI_API_KEY"] = API_KEY
            except Exception:
                pass
            console.print("[green]✓ Anahtar şifrelendi ve yerel olarak kaydedildi. Uzaktaki modeller artık sizin anahtarınızla kullanılacak.[/green]")
        except Exception as e:
            console.print(f"[red]Anahtar kaydedilemedi: {e}[/red]")
        # Keep current model unchanged
        return current_model or models[0]["id"]
    
    # Otherwise: list models and select
    console.print("\n[bold #C8A882]═══ Model Seçimi ═══[/bold #C8A882]\n")
    local_models = [m for m in models if m.get("type") == "local"]
    remote_models = [m for m in models if m.get("type") == "remote"]
    display_models = local_models + remote_models
    
    if local_models:
        console.print("[bold green]🏠 Lokal Modeller (Ollama):[/bold green]\n")
        for i, model in enumerate(local_models, 1):
            console.print(f"[#C8A882]{i}.[/#C8A882] [bold green]{model['name']}[/bold green]")
            console.print(f"   {model['description']}")
            console.print(f"   [dim]ID: {model['id']}[/dim]\n")
    
    if remote_models:
        start_num = len(local_models) + 1
        console.print("[bold blue]🌐 Uzaktaki Modeller (OpenRouter):[/bold blue]\n")
        console.print("[dim]Not: Uzaktaki modelleri kullanmak için kendi OpenRouter anahtarınızı girmeniz gerekir (\\ menüsünden).[/dim]\n")
        for i, model in enumerate(remote_models, start_num):
            console.print(f"[#C8A882]{i}.[/#C8A882] [bold blue]{model['name']}[/bold blue]")
            console.print(f"   {model['description']}")
            console.print(f"   [dim]ID: {model['id']}[/dim]\n")
    
    while True:
        try:
            choice = Prompt.ask("[#C8A882]Model seçin[/#C8A882]", default="1")
            choice_num = int(choice)
            if 1 <= choice_num <= len(display_models):
                selected_model = display_models[choice_num - 1]
                model_type = "🏠 Lokal" if selected_model.get("type") == "local" else "🌐 Uzaktan"
                console.print(f"\n[green]✓ Seçildi: {selected_model['name']} ({model_type})[/green]\n")
                # Persist active model
                settings = load_user_settings()
                settings["active_model_id"] = selected_model["id"]
                settings["active_model_name"] = selected_model["name"]
                save_user_settings(settings)
                return selected_model["id"]
            else:
                console.print(f"[red]Lütfen 1-{len(display_models)} arasında bir sayı girin[/red]")
        except ValueError:
            console.print("[red]Lütfen geçerli bir sayı girin[/red]")
        except KeyboardInterrupt:
            console.print("\n[yellow]Varsayılan model kullanılacak[/yellow]")
            return display_models[0]["id"]


class ProjectState:
    """Manages project state persistence for long-term projects"""
    
    def __init__(self, project_dir: str = ".cli_projects"):
        self.project_dir = Path(project_dir).resolve()
        self.project_dir.mkdir(exist_ok=True)
    
    def _validate_project_id(self, project_id: str) -> bool:
        """Validate project_id to prevent path traversal attacks"""
        if not re.match(r'^[A-Za-z0-9_-]+$', project_id):
            return False
        project_file = (self.project_dir / f"{project_id}.json").resolve()
        return self.project_dir in project_file.parents
    
    def save_project(self, project_id: str, data: Dict):
        """Save project state to file"""
        if not self._validate_project_id(project_id):
            raise ValueError(f"Invalid project ID: {project_id}")
        project_file = self.project_dir / f"{project_id}.json"
        with open(project_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load_project(self, project_id: str) -> Optional[Dict]:
        """Load project state from file"""
        if not self._validate_project_id(project_id):
            return None
        project_file = self.project_dir / f"{project_id}.json"
        if project_file.exists():
            with open(project_file, 'r') as f:
                return json.load(f)
        return None
    
    def list_projects(self) -> List[Dict]:
        """List all saved projects"""
        projects = []
        for project_file in self.project_dir.glob("*.json"):
            try:
                with open(project_file, 'r') as f:
                    data = json.load(f)
                    steps_list = data.get("steps", [])
                    cur_step = data.get("current_step", 0)
                    sub_map = data.get("substeps_map", {})
                    next_step = cur_step + 1 if cur_step < len(steps_list) else cur_step
                    sub_total = len(sub_map.get(str(next_step), [])) if isinstance(sub_map, dict) else 0
                    cur_sub = data.get("current_substep", 0) if sub_total > 0 else 0
                    projects.append({
                        "id": project_file.stem,
                        "name": data.get("task_name", "Unknown"),
                        "created": data.get("created_at", "Unknown"),
                        "status": data.get("status", "Unknown"),
                        "current_step": cur_step,
                        "total_steps": len(steps_list),
                        "subprogress": f"{cur_sub}/{sub_total}" if sub_total > 0 else "-"
                    })
            except Exception:
                pass
        return sorted(projects, key=lambda x: x.get("created", ""), reverse=True)
    
    def delete_project(self, project_id: str):
        """Delete a project"""
        if not self._validate_project_id(project_id):
            raise ValueError(f"Invalid project ID: {project_id}")
        project_file = self.project_dir / f"{project_id}.json"
        if project_file.exists():
            project_file.unlink()


class ResponseParser:
    """Parses AI responses and extracts file operations"""
    
    @staticmethod
    def parse_and_execute(response: str) -> Dict:
        """Parse AI response and execute file operations"""
        results = {
            "files_created": [],
            "folders_created": [],
            "errors": [],
            "operations": 0,
            "diffs": []
        }
        
        try:
            # Pattern 1: CREATE_FILE: path/to/file.ext
            file_pattern = r'CREATE_FILE:\s*([^\n]+)\s*```(\w+)?\s*(.*?)```'
            for match in re.finditer(file_pattern, response, re.DOTALL):
                file_path = match.group(1).strip()
                content = match.group(3).strip()
                
                # If file exists, compute a unified diff for verification
                try:
                    if os.path.exists(file_path):
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            old_content = f.read()
                        diff_text = '\n'.join(difflib.unified_diff(
                            old_content.splitlines(),
                            content.splitlines(),
                            fromfile=f"old:{file_path}",
                            tofile=f"new:{file_path}",
                            lineterm=''
                        ))
                        if diff_text.strip():
                            results["diffs"].append({"file": file_path, "diff": diff_text})
                except Exception as e:
                    # Diff calculation should not block file creation
                    results["errors"].append(f"Diff error for {file_path}: {str(e)}")
                
                # Ensure parent folder and pre-create file synchronously before writing
                try:
                    parent = str(Path(file_path).parent)
                    if parent:
                        execute_safe_command("create_folder", folder_path=parent)
                    pre = execute_safe_command("create_empty_file", file_path=file_path, create_dirs=True)
                    if not pre.get("success") and not pre.get("already_exists"):
                        results["errors"].append(f"Failed to pre-create {file_path}: {pre.get('error')}")
                except Exception as e:
                    results["errors"].append(f"Pre-create error for {file_path}: {str(e)}")
                
                # Write content to the already existing file
                result = execute_safe_command("write_file", file_path=file_path, content=content)
                if result.get("success"):
                    results["files_created"].append(file_path)
                    results["operations"] += 1
                else:
                    results["errors"].append(f"Failed to write {file_path}: {result.get('error')}")
            
            # Pattern 2: CREATE_PROJECT: project_name with JSON structure
            project_pattern = r'CREATE_PROJECT:\s*([^\n]+)\s*```json\s*(.*?)```'
            for match in re.finditer(project_pattern, response, re.DOTALL):
                project_name = match.group(1).strip()
                try:
                    structure = json.loads(match.group(2).strip())
                    result = execute_safe_command("create_project_structure", 
                                                  project_name=project_name, 
                                                  structure=structure)
                    if result.get("success"):
                        results["folders_created"].append(project_name)
                        results["operations"] += 1
                    else:
                        results["errors"].append(f"Failed to create project {project_name}: {result.get('error')}")
                except json.JSONDecodeError as e:
                    results["errors"].append(f"Invalid JSON for project {project_name}: {str(e)}")
            
            # Pattern 3: CREATE_FOLDER: path/to/folder
            folder_pattern = r'CREATE_FOLDER:\s*([^\n]+)'
            for match in re.finditer(folder_pattern, response):
                folder_path = match.group(1).strip()
                result = execute_safe_command("create_folder", folder_path=folder_path)
                if result.get("success"):
                    results["folders_created"].append(folder_path)
                    results["operations"] += 1
                else:
                    results["errors"].append(f"Failed to create folder {folder_path}: {result.get('error')}")
                    
        except Exception as e:
            results["errors"].append(f"Parser error: {str(e)}")
        
        return results

    @staticmethod
    async def parse_and_execute_async(response: str) -> Dict:
        """Async parser to execute file operations and safe run commands."""
        results = {
            "files_created": [],
            "folders_created": [],
            "errors": [],
            "operations": 0,
            "diffs": [],
            "commands_run": []
        }
        
        try:
            # Reuse synchronous parsing for file/folder/project creation
            sync_results = ResponseParser.parse_and_execute(response)
            for k in ["files_created", "folders_created", "errors", "operations", "diffs"]:
                if k == "operations":
                    results["operations"] += sync_results.get(k, 0)
                else:
                    results[k].extend(sync_results.get(k, []))
            
            # Pattern 4: LAUNCH auto and background process commands
            # LAUNCH: auto => auto-detect project and start dev server, parse local address
            launch_pattern = r'LAUNCH:\s*([^\n]+)'
            for match in re.finditer(launch_pattern, response):
                token = match.group(1).strip()
                try:
                    if token.lower() == "auto":
                        launch_res = await execute_safe_command_async("launch_auto", cwd=str(Path.cwd()))
                        results["operations"] += 1
                        results.setdefault("launches", []).append({
                            "mode": "auto",
                            "success": launch_res.get("success"),
                            "address": launch_res.get("address"),
                            "pid": launch_res.get("pid"),
                            "command": launch_res.get("command"),
                            "error": launch_res.get("error"),
                        })
                        if not launch_res.get("success") and launch_res.get("error"):
                            results["errors"].append(f"Launch error: {launch_res.get('error')}")
                    else:
                        # Treat LAUNCH: <command> as explicit background process
                        bg_res = await execute_safe_command_async("run_command_bg", command=token, cwd=str(Path.cwd()))
                        results["operations"] += 1
                        results.setdefault("processes", []).append({
                            "command": token,
                            "success": bg_res.get("success"),
                            "pid": bg_res.get("pid"),
                            "error": bg_res.get("error"),
                        })
                        if not bg_res.get("success") and bg_res.get("error"):
                            results["errors"].append(f"Launch error: {bg_res.get('error')}")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    results["errors"].append(f"Launch execution failed: {str(e)}")

            # Pattern 5: RUN_BG / STOP_BG / RESTART_BG
            bg_run_pattern = r'RUN_BG:\s*([^\n]+)'
            for match in re.finditer(bg_run_pattern, response):
                cmd = match.group(1).strip()
                try:
                    bg_res = await execute_safe_command_async("run_command_bg", command=cmd, cwd=str(Path.cwd()))
                    results["operations"] += 1
                    results.setdefault("processes", []).append({
                        "command": cmd,
                        "success": bg_res.get("success"),
                        "pid": bg_res.get("pid"),
                        "error": bg_res.get("error"),
                    })
                    if not bg_res.get("success") and bg_res.get("error"):
                        results["errors"].append(f"Background run error: {bg_res.get('error')}")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    results["errors"].append(f"Background run failed: {str(e)}")

            stop_bg_pattern = r'STOP_BG:\s*(\S+)'
            for match in re.finditer(stop_bg_pattern, response):
                target = match.group(1).strip()
                try:
                    stop_res = await execute_safe_command_async("stop_process", pid=target)
                    results["operations"] += 1
                    results.setdefault("stops", []).append({
                        "target": target,
                        "success": stop_res.get("success"),
                        "error": stop_res.get("error"),
                    })
                    if not stop_res.get("success") and stop_res.get("error"):
                        results["errors"].append(f"Stop error: {stop_res.get('error')}")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    results["errors"].append(f"Stop failed: {str(e)}")

            restart_bg_pattern = r'RESTART_BG:\s*(\S+)'
            for match in re.finditer(restart_bg_pattern, response):
                target = match.group(1).strip()
                try:
                    restart_res = await execute_safe_command_async("restart_process", pid=target)
                    results["operations"] += 1
                    results.setdefault("restarts", []).append({
                        "target": target,
                        "success": restart_res.get("success"),
                        "pid": restart_res.get("pid"),
                        "error": restart_res.get("error"),
                    })
                    if not restart_res.get("success") and restart_res.get("error"):
                        results["errors"].append(f"Restart error: {restart_res.get('error')}")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    results["errors"].append(f"Restart failed: {str(e)}")

            # Pattern 6: RUN / RUN_TEST commands
            run_pattern = r'RUN(?:_TEST|_COMMAND)?:\s*([^\n]+)'
            for match in re.finditer(run_pattern, response):
                command = match.group(1).strip()
                # Run with cancellation support
                try:
                    run_res = await execute_safe_command_async("run_command", command=command)
                    results["commands_run"].append({
                        "command": command,
                        "success": run_res.get("success"),
                        "exit_code": run_res.get("exit_code"),
                        "stdout": run_res.get("stdout", "")[:4000],
                        "stderr": run_res.get("stderr", "")[:4000],
                        "error": run_res.get("error")
                    })
                    results["operations"] += 1
                    if not run_res.get("success") and run_res.get("error"):
                        results["errors"].append(f"Run error: {run_res.get('error')}")
                except asyncio.CancelledError:
                    # If sub-step is cancelled while running command, propagate
                    raise
                except Exception as e:
                    results["errors"].append(f"Run execution failed: {str(e)}")
        except asyncio.CancelledError:
            # Propagate cancellation
            raise
        except Exception as e:
            results["errors"].append(f"Async parser error: {str(e)}")
        
        return results


class AIClient:
    """Handles communication with the AI API (both remote and local Ollama)"""
    
    def __init__(self, model: str, key_manager: Optional[KeyStore] = None):
        self.api_key = API_KEY
        self.model = model
        self.endpoint = API_ENDPOINT
        self.is_ollama = model.startswith("ollama/")
        self.key_manager = key_manager
        
        if self.is_ollama:
            # Extract actual model name for Ollama
            self.ollama_model = model.replace("ollama/", "")
            self.ollama_endpoint = "http://localhost:11434/api/chat"
    
    async def send_message(self, messages: List[Dict], temperature: float = 0.7) -> str:
        """Send a message to the AI and get a response"""
        
        if self.is_ollama:
            return await self._send_ollama_message(messages, temperature)
        else:
            return await self._send_remote_message(messages, temperature)
    
    async def _send_ollama_message(self, messages: List[Dict], temperature: float = 0.7) -> str:
        """Send message to local Ollama"""
        try:
            payload = {
                "model": self.ollama_model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature
                }
            }
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    self.ollama_endpoint,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                return data["message"]["content"]
        except httpx.HTTPError as e:
            console.print(f"[red]Ollama API Error: {e}[/red]")
            console.print("[yellow]Make sure Ollama is running: ollama serve[/yellow]")
            return ""
        except Exception as e:
            console.print(f"[red]Ollama connection error: {e}[/red]")
            return ""
    
    async def _send_remote_message(self, messages: List[Dict], temperature: float = 0.7) -> str:
        """Send message to remote API (OpenRouter) - requires user's own API key"""
        # Prefer the user's saved key, but gracefully fall back to .env AI_API_KEY if available
        user_key = None
        try:
            if self.key_manager:
                if self.key_manager.use_user_key():
                    user_key = self.key_manager.get_user_key()
                else:
                    # Flag is off; try environment key as fallback
                    user_key = self.api_key
        except Exception:
            user_key = None
        # Fallback to environment variable if keystore returns nothing
        if not user_key and self.api_key:
            user_key = self.api_key
        
        if not user_key:
            # Diagnostics to help user resolve quickly
            ks_state = None
            try:
                if self.key_manager:
                    ks_state = {
                        "use_user_key": self.key_manager.use_user_key(),
                        "has_user_key": self.key_manager.has_user_key()
                    }
            except Exception:
                ks_state = None
            console.print("[red]OpenRouter API anahtarı eksik.[/red]")
            console.print("[yellow]Çözüm: \\ menüsünden 'Kendi OpenRouter API Anahtarını Gir' seçeneğini kullanın veya .env dosyasına AI_API_KEY ekleyin.[/yellow]")
            if ks_state is not None:
                console.print(f"[dim]Tanılama - use_user_key: {ks_state['use_user_key']}, has_user_key: {ks_state['has_user_key']}[/dim]")
            return ""
        
        headers = {
            "Authorization": f"Bearer {user_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://custom-cli-tool.local",
            "X-Title": "Custom CLI Tool"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    self.endpoint,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except httpx.HTTPError as e:
            console.print(f"[red]API Hatası: {e}[/red]")
            return ""
        except Exception as e:
            console.print(f"[red]Beklenmeyen hata: {e}[/red]")
            return ""


class TaskPlanner:
    """Analyzes tasks and breaks them down into steps"""
    
    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
    
    async def analyze_task(self, user_input: str) -> Dict:
        """Determine if task needs step-by-step breakdown or simple response"""
        
        analysis_prompt = f"""Analyze this input and categorize it:

CATEGORY 1 - Normal Conversation/Question (respond with "conversation"):
- Casual questions or greetings
- Requests for information or explanations
- Short questions with straightforward answers
- General knowledge questions

CATEGORY 2 - Project/File Work (respond with "project"):
- Creating, modifying, or working with files
- Building applications or systems (web apps, mobile apps, games, etc.)
- Multi-step technical tasks
- Code development or refactoring
- File system operations

User Input: {user_input}

If this is CATEGORY 2 (project work), break it into DETAILED steps (20-30+ steps for complex projects).
Each step should be a CONCRETE action that creates or modifies specific files.

For web/mobile projects, steps should include:
1. Create project structure
2. Create each HTML/component file
3. Create each CSS/styling file
4. Create each JavaScript/logic file
5. Add features one by one
6. Configure settings/dependencies

Respond in JSON format:
{{
    "mode": "conversation" or "project",
    "is_complex": true/false,
    "task_name": "brief name" or null,
    "steps": ["step 1", "step 2", ...] or null,
    "reasoning": "why this categorization"
}}"""
        
        messages = [
            {"role": "system", "content": "You are a task categorization expert. Distinguish between casual conversations and project work that needs step-by-step execution."},
            {"role": "user", "content": analysis_prompt}
        ]
        
        with Progress(
            SpinnerColumn(spinner_name="dots", style="#C8A882"),
            TextColumn("[#C8A882][progress.description]{task.description}[/#C8A882]"),
            console=console
        ) as progress:
            progress.add_task(description="Thinking...", total=None)
            response = await self.ai_client.send_message(messages, temperature=0.3)
        
        try:
            response = response.strip()
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()
            
            ret = json.loads(response)
            # V6 dynamic adaptation: ensure robust step count and concurrency hints
            if isinstance(ret, dict) and (ret.get("mode") == "project"):
                try:
                    from thinking_python import estimate_task_complexity, break_down_task
                    comp = estimate_task_complexity(user_input)
                    level = comp.get("level", "medium")
                    mapped = "small" if level == "low" else ("large" if level == "high" else "medium")
                    base_steps = comp.get("estimated_steps", 7)
                    if mapped == "small":
                        target = max(3, min(6, base_steps))
                    elif mapped == "medium":
                        target = max(7, min(12, base_steps + 3))
                    else:
                        target = max(13, min(25, base_steps + 10))
                    steps = ret.get("steps") or []
                    if not steps or len(steps) < max(3, target // 2):
                        steps = break_down_task(user_input, num_steps=target)
                        ret["steps"] = steps
                    ret["is_complex"] = mapped != "small"
                    ret["complexity"] = {
                        "level": mapped,
                        "estimated_steps": len(ret.get("steps") or []),
                        "suggested_concurrency": 2 if mapped == "small" else (3 if mapped == "medium" else 4)
                    }
                    if not ret.get("task_name"):
                        ret["task_name"] = (user_input[:40] + "...") if len(user_input) > 40 else user_input
                except Exception:
                    pass
            return ret
        except json.JSONDecodeError:
            return {
                "mode": "conversation",
                "is_complex": False,
                "task_name": None,
                "steps": None,
                "reasoning": "Could not parse analysis, defaulting to conversation mode"
            }


class StepExecutor:
    """Executes tasks step by step with pause and re-evaluation"""
    
    def __init__(self, ai_client: AIClient, project_state: ProjectState):
        self.ai_client = ai_client
        self.project_state = project_state
        self.conversation_history = []
        self.current_project_name = None
        # Simple memory store to improve reasoning across steps
        self.memory = {
            "decisions": [],
            "summaries": [],
            "files_created": [],
            "folders_created": []
        }
        # Concurrency control for sub-steps
        self._substep_sem = asyncio.Semaphore(2)
        self.max_concurrency = 2
        # Stop control
        self._stop_requested = False
        self._current_substep_tasks = []
        self.current_project_id = None

    def request_stop(self):
        """Request to stop execution and cancel any active sub-step tasks."""
        self._stop_requested = True
        for t in getattr(self, "_current_substep_tasks", []):
            try:
                if t and not t.done():
                    t.cancel()
            except Exception:
                pass

    async def _generate_substeps(self, step_desc: str) -> List[str]:
        """Generate actionable sub-steps for a given main step."""
        from thinking_python import break_down_task, estimate_task_complexity
        complexity = estimate_task_complexity(step_desc)
        # Aim 3-8 sub-steps depending on complexity
        num = max(3, min(8, complexity.get("estimated_steps", 5) + (2 if complexity.get("level") == "high" else 1)))
        substeps = break_down_task(step_desc, num_steps=num)
        # Ensure substeps are actionable and specific
        normalized = []
        for idx, s in enumerate(substeps, 1):
            s_clean = s.strip()
            if not s_clean:
                s_clean = f"Alt görev {idx}"
            # Prefix to nudge code/file creation
            if not re.search(r"create|build|implement|update|generate|write", s_clean, re.IGNORECASE):
                s_clean = f"Implement: {s_clean}"
            normalized.append(s_clean)
        return normalized

    async def _run_substep(self, i: int, j: int, sub: str, context: str, results: List[str], permission_granted: bool,
                           substeps_map: Dict[str, List[str]], project_id: str, task_name: str, original_input: str,
                           saved_state: Optional[Dict], steps: List[str]):
        """Execute a single sub-step in a concurrency-controlled block and persist progress immediately."""
        from thinking_python import prevent_hallucination_in_long_tasks, classify_defects
        async with self._substep_sem:
            try:
                console.print(f"\n[#C8A882]→ Executing sub-step {i}.{j}/{i}.{len(substeps_map.get(str(i), []))}: {sub}[/#C8A882]")
                trimmed_context = prevent_hallucination_in_long_tasks(context)
                # Build sub-step prompt with recent results
                step_context = f"{trimmed_context}\n\nPrevious steps completed:\n"
                for pj, prev_result in enumerate(results, 1):
                    step_context += f"\nStep {pj} Result:\n{prev_result}\n"
                sub_prompt = (
                    f"\nNow execute Sub-step {i}.{j} (of Step {i}): {sub}\n"
                    f"Focus on a small, atomic change and CREATE WORKING CODE FILES."
                )
                system_prompt = """You are Oroto AI, executing a multi-step task with sub-steps. You are a CODING assistant - create actual code files immediately.

CRITICAL RULES:
1. DO NOT just describe or plan - CREATE FILES WITH CODE at EVERY sub-step
2. Each sub-step MUST create at least one file with actual working code
3. Use the file creation commands - they will execute automatically

COMMANDS TO CREATE FILES:

1. CREATE A SINGLE FILE WITH CODE:
CREATE_FILE: path/to/filename.ext
```language
actual working code here
```

2. CREATE PROJECT WITH MULTIPLE FILES:
CREATE_PROJECT: project_name
```json
{
  "folder1": {
    "file1.html": "<!DOCTYPE html>...complete code...",
    "file2.css": "complete css code..."
  }
}
```

3. CREATE FOLDER:
CREATE_FOLDER: path/to/folder

4. RUN TESTS/COMMANDS (safe & interruptible):
RUN: npm test
RUN_TEST: pytest -q

EXECUTION RULES:
1. START CODING IMMEDIATELY - don't just plan
2. Each sub-step = create actual files with real code
3. For web/mobile apps: Create HTML, CSS, JS files with complete code
4. Write FULL, WORKING code in each file - not placeholders
5. Build feature by feature, file by file
6. Keep descriptions brief - focus on creating files
"""
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": step_context + "\n\n" + sub_prompt}
                ]
                # Deterministic, error-minimizing generation
                with Progress(
                    SpinnerColumn(spinner_name="dots", style="#C8A882"),
                    TextColumn("[#C8A882]Thinking...[/#C8A882]"),
                    console=console
                ) as progress:
                    progress.add_task(description="", total=None)
                    response = await self.ai_client.send_message(messages, temperature=0.2)
                if not response:
                    console.print(f"[red]No response for sub-step {i}.{j}. Skipping.[/red]")
                else:
                    console.print(Panel(Markdown(response), title=f"[bold #C8A882]AI - Step {i}.{j}[/bold #C8A882]", border_style="#C8A882"))
                    results.append(response)
                    parse_results = await ResponseParser.parse_and_execute_async(response)
                    # Show diffs for verification
                    if parse_results.get("diffs"):
                        for d in parse_results["diffs"]:
                            console.print(Panel(Markdown(f"```diff\n{d['diff']}\n```"), title=f"[bold magenta]Diff[/bold magenta]: {d['file']}", border_style="magenta"))
                    # Memory updates
                    if parse_results.get("files_created"):
                        self.memory["files_created"].extend(parse_results["files_created"])
                    if parse_results.get("folders_created"):
                        self.memory["folders_created"].extend(parse_results["folders_created"])
                    if parse_results.get("errors"):
                        classification = classify_defects(parse_results["errors"])
                        console.print(f"[dim]Defect classification: {classification['summary']}[/dim]")
                        # One retry attempt
                        fix_prompt = (
                            f"Errors occurred during Sub-step {i}.{j}. Please fix the issues and re-create files if needed.\n"
                            f"Errors: {parse_results['errors']}"
                        )
                        retry_messages = [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": step_context + "\n\n" + sub_prompt + "\n\n" + fix_prompt}
                        ]
                        with Progress(
                            SpinnerColumn(spinner_name="dots", style="#C8A882"),
                            TextColumn("[#C8A882]Retrying...[/#C8A882]"),
                            console=console
                        ) as progress:
                            progress.add_task(description="", total=None)
                            retry_resp = await self.ai_client.send_message(retry_messages, temperature=0.2)
                        if retry_resp:
                            console.print(Panel(Markdown(retry_resp), title=f"[bold #C8A882]AI - Step {i}.{j} Retry[/bold #C8A882]", border_style="#C8A882"))
                            retry_parse = await ResponseParser.parse_and_execute_async(retry_resp)
                            if retry_parse.get("operations", 0) > 0:
                                console.print(f"[green]✓ Retry executed {retry_parse['operations']} additional operation(s)[/green]")
                            if retry_parse.get("files_created"):
                                self.memory["files_created"].extend(retry_parse["files_created"])
                            if retry_parse.get("folders_created"):
                                self.memory["folders_created"].extend(retry_parse["folders_created"])
                # Mark sub-step complete immediately
                current_substep = j
                # Append a short summary to memory
                summary_line = f"Step {i}.{j} → ops:{parse_results.get('operations',0)} files:{len(parse_results.get('files_created',[]))} folders:{len(parse_results.get('folders_created',[]))} commands:{len(parse_results.get('commands_run',[]))}"
                self.memory["summaries"].append(summary_line)
                # Persist progress including memory
                project_data = {
                    "project_id": project_id,
                    "task_name": task_name,
                    "original_input": original_input,
                    "steps": steps,
                    "current_step": i - 1,
                    "current_substep": current_substep,
                    "results": results,
                    "context": context,
                    "permission_granted": permission_granted,
                    "substeps_map": substeps_map,
                    "status": "in_progress",
                    "created_at": saved_state.get("created_at", datetime.now().isoformat()) if saved_state else datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "memory": self.memory
                }
                self.project_state.save_project(project_id, project_data)

            except asyncio.CancelledError:
                # Persist partial project state on cancellation
                partial_data = {
                    "project_id": project_id,
                    "task_name": task_name,
                    "original_input": original_input,
                    "steps": steps,
                    "current_step": i - 1,
                    "current_substep": max(0, j - 1),
                    "results": results,
                    "context": context,
                    "permission_granted": permission_granted,
                    "substeps_map": substeps_map,
                    "status": "stopped",
                    "created_at": saved_state.get("created_at", datetime.now().isoformat()) if saved_state else datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "memory": self.memory
                }
                self.project_state.save_project(project_id, partial_data)
                console.print("[bold yellow]Sub-step cancelled by user. Partial progress saved.[/bold yellow]")
                raise

    async def execute_simple_task(self, user_input: str):
        """Quick single-response execution for conversation mode."""
        from thinking_python import sanitize_input, prevent_hallucination_in_long_tasks
        clean_input = sanitize_input(user_input)
        messages = [
            {"role": "system", "content": "You are Oroto AI, a helpful assistant. Provide concise, accurate answers. If user requests code, include full working code between triple backticks. Avoid destructive commands."},
            {"role": "user", "content": clean_input}
        ]
        with Progress(
            SpinnerColumn(spinner_name="dots", style="#C8A882"),
            TextColumn("[#C8A882]Thinking...[/#C8A882]"),
            console=console
        ) as progress:
            progress.add_task(description="", total=None)
            response = await self.ai_client.send_message(messages, temperature=0.5)
        if not response:
            console.print("[red]No response received from AI.[/red]")
            return
        self.conversation_history.append({"user": user_input, "assistant": response})
        console.print(Panel(Markdown(response), title="[bold #C8A882]AI Response[/bold #C8A882]", border_style="#C8A882"))

    async def execute_complex_task(self, task_name: str, steps: List[str], original_input: str, project_id: Optional[str] = None, complexity_hint: Optional[Dict] = None):
        """Execute a complex project with sub-steps, concurrency, and persistent memory."""
        from thinking_python import prevent_hallucination_in_long_tasks, create_version_snapshot, sanitize_input
        # Prepare or resume project state
        self.current_project_name = task_name
        clean_input = sanitize_input(original_input)
        context = f"Project: {task_name}\nOriginal Request:\n{clean_input}\n\nPlanned Steps ({len(steps)}):\n" + "\n".join([f"{idx+1}. {s}" for idx, s in enumerate(steps)])

        permission_granted = False
        results: List[str] = []
        substeps_map: Dict[str, List[str]] = {}
        current_step_completed = 0
        current_substep = 0
        saved_state = None

        if project_id:
            saved_state = self.project_state.load_project(project_id)
            if saved_state:
                permission_granted = saved_state.get("permission_granted", False)
                results = saved_state.get("results", [])
                substeps_map = saved_state.get("substeps_map", {}) or {}
                current_step_completed = saved_state.get("current_step", 0)
                current_substep = saved_state.get("current_substep", 0)
                # Restore memory if present
                mem = saved_state.get("memory")
                if isinstance(mem, dict):
                    self.memory.update(mem)

        if not project_id:
            # Generate a safe project_id
            base = re.sub(r"[^A-Za-z0-9_-]+", "-", task_name.strip())[:40].strip("-")
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            project_id = base.lower() if base else f"proj-{timestamp}"
            project_id = project_id if re.match(r"^[A-Za-z0-9_-]+$", project_id) else f"proj-{timestamp}"

        # Ask permission once if not previously granted
        if not permission_granted:
            console.print(Panel.fit(f"This operation will CREATE/MODIFY files and folders to build:\n[bold]{task_name}[/bold]\nProceed?", border_style="#C8A882", title="[bold #C8A882]Permission Required[/bold #C8A882]"))
            permission_granted = Confirm.ask("[#C8A882]Allow file operations?[/#C8A882]")

        # Workspace isolation per project
        if saved_state and saved_state.get("workspace"):
            workspace_dir = Path(saved_state["workspace"]).resolve()
        else:
            workspace_dir = (BASE_DIR / "Workspace" / project_id).resolve()
        try:
            workspace_dir.mkdir(parents=True, exist_ok=True)
            (workspace_dir / ".logs").mkdir(parents=True, exist_ok=True)
            os.chdir(str(workspace_dir))
            console.print(f"[dim]Workspace: {workspace_dir}[/dim]")
        except Exception as e:
            console.print(f"[yellow]Workspace setup warning: {e}[/yellow]")

        # Initial save
        project_data = {
            "project_id": project_id,
            "task_name": task_name,
            "original_input": original_input,
            "steps": steps,
            "current_step": current_step_completed,
            "current_substep": current_substep,
            "results": results,
            "context": context,
            "permission_granted": permission_granted,
            "substeps_map": substeps_map,
            "status": "in_progress",
            "created_at": saved_state.get("created_at", datetime.now().isoformat()) if saved_state else datetime.now().isoformat(),
            "last_updated": saved_state.get("last_updated", datetime.now().isoformat()) if saved_state else datetime.now().isoformat(),
            "memory": self.memory,
            "workspace": str(workspace_dir)
        }
        self.project_state.save_project(project_id, project_data)
        self.current_project_id = project_id

        # Apply dynamic concurrency based on V6 complexity hints
        try:
            k = self.max_concurrency
            if complexity_hint and isinstance(complexity_hint, dict):
                k = int(complexity_hint.get("suggested_concurrency", k))
            k = max(1, min(8, k))
            if k != self.max_concurrency:
                self.max_concurrency = k
                self._substep_sem = asyncio.Semaphore(k)
                console.print(f"[dim]Parallel substep concurrency set to {k}[/dim]")
        except Exception:
            pass

        # Execute each remaining step
        total_steps = len(steps)
        try:
            for i in range(current_step_completed + 1, total_steps + 1):
                step_desc = steps[i - 1]
                console.print(Panel.fit(f"[bold]Step {i}/{total_steps}[/bold]\n{step_desc}", border_style="#C8A882", title="[bold #C8A882]Executing Step[/bold #C8A882]"))
            # Generate substeps if not already present
            if str(i) not in substeps_map:
                substeps_map[str(i)] = await self._generate_substeps(step_desc)
                # Persist substeps plan
                project_data["substeps_map"] = substeps_map
                project_data["last_updated"] = datetime.now().isoformat()
                self.project_state.save_project(project_id, project_data)

            substeps = substeps_map.get(str(i), [])
            if not substeps:
                console.print("[yellow]No sub-steps generated; executing step directly.[/yellow]")

            # Execute sub-steps in parallel with concurrency control
            current_substep = 0
            before_file_count = len(self.memory.get("files_created", []))
            tasks = []
            for j, sub in enumerate(substeps, 1):
                t = asyncio.create_task(self._run_substep(i, j, sub, context, results, permission_granted, substeps_map, project_id, task_name, original_input, saved_state, steps))
                tasks.append(t)
            self._current_substep_tasks = tasks
            if tasks:
                await asyncio.gather(*tasks)
                current_substep = len(substeps)
            self._current_substep_tasks = []
            after_file_count = len(self.memory.get("files_created", []))
            new_files_this_step = self.memory.get("files_created", [])[before_file_count:after_file_count]

            # Create snapshot after step completion
            try:
                snap = create_version_snapshot(project_id, i, new_files_this_step)
                if snap.get("success"):
                    console.print(f"[green]✓ Snapshot saved: {snap.get('snapshot_id')}[/green]")
                else:
                    console.print(f"[yellow]Snapshot warning: {snap.get('message')}[/yellow]")
            except Exception as e:
                console.print(f"[yellow]Snapshot failed: {e}[/yellow]")

            # Update memory with step summary/decision
            decision_summary = f"Completed Step {i}: {step_desc} → files:{len(new_files_this_step)}"
            self.memory["decisions"].append(decision_summary)

            # Persist progress after step completion
            project_data.update({
                "current_step": i,
                "current_substep": current_substep,
                "results": results,
                "permission_granted": permission_granted,
                "substeps_map": substeps_map,
                "last_updated": datetime.now().isoformat(),
                "memory": self.memory
            })
            self.project_state.save_project(project_id, project_data)

            # Show progress
            console.print(f"[#C8A882]Progress: {i}/{total_steps} steps completed. Substeps: {current_substep}/{len(substeps)}[/#C8A882]")
        except asyncio.CancelledError:
            # Save current project state and exit gracefully
            project_data["status"] = "stopped"
            project_data["last_updated"] = datetime.now().isoformat()
            self.project_state.save_project(project_id, project_data)
            console.print("[bold yellow]Process stopped by user. Project state saved.[/bold yellow]")
            raise

        # Finalization
        project_data["status"] = "completed"
        project_data["last_updated"] = datetime.now().isoformat()
        self.project_state.save_project(project_id, project_data)

        # Auto-launch dev server if applicable and show address
        try:
            ws = project_data.get("workspace")
            res = await execute_safe_command_async("launch_auto", cwd=ws or str(Path.cwd()))
            if res.get("success"):
                addrs = res.get("addresses") or []
                addr = addrs[0] if addrs else None
                # Give the process a moment to print its URL
                await asyncio.sleep(1.5)
                # Try to refresh addresses from registry
                procs = await execute_safe_command_async("list_processes")
                if procs.get("success") and res.get("pid"):
                    for p in procs.get("processes", []):
                        if p.get("pid") == res.get("pid"):
                            addrs = p.get("addresses") or addrs
                            break
                addr = addrs[0] if addrs else addr
                msg = f"Launched dev server (pid {res.get('pid')})."
                if addr:
                    msg += f" Access: {addr}"
                console.print(Panel.fit(f"[green]✓ {msg}[/green]", border_style="#C8A882", title="[bold #C8A882]Auto-Run[/bold #C8A882]"))
            else:
                console.print(f"[dim]Auto-launch skipped: {res.get('error')}[/dim]")
        except Exception as e:
            console.print(f"[yellow]Auto-launch warning: {e}[/yellow]")

        console.print(Panel.fit(f"[bold green]Project '{task_name}' completed![/bold green]\nID: {project_id}", border_style="#C8A882", title="[bold #C8A882]Done[/bold #C8A882]"))


async def main():
    """Main CLI entry point"""
    
    # Show Oroto logo on startup
    console.print()
    console.print(Panel.fit(
        "[bold #C8A882]   ___  ____   ___ _____ ___  [/bold #C8A882]\n"
        "[bold #C8A882]  / _ \\|  _ \\ / _ \\_   _/ _ \\ [/bold #C8A882]\n"
        "[bold #C8A882] | | | | |_) | | | || || | | |[/bold #C8A882]\n"
        "[bold #C8A882] | |_| |  _ <| |_| || || |_| |[/bold #C8A882]\n"
        "[bold #C8A882]  \\___/|_| \\_\\\\___/ |_| \\___/ [/bold #C8A882]\n\n"
        "[dim]AI Assistant for Projects & Conversations[/dim]\n"
        "[dim]Commands: list | resume <id> | delete <id> | ps | logs <pid> [n] | launch <id> | kill <pid> | stop-all | runbg <cmd> | quit | \\ (model / anahtar menüsü)[/dim]",
        border_style="#C8A882",
        title="[bold #C8A882]Welcome[/bold #C8A882]"
    ))
    
    # Use saved model if available, otherwise prefer local Ollama
    models = load_models()
    settings = load_user_settings()
    saved_id = settings.get("active_model_id")
    if saved_id and any(m["id"] == saved_id for m in models):
        current_model = saved_id
        current_model_name = next(m["name"] for m in models if m["id"] == saved_id)
    else:
        local_first = next((m for m in models if m.get("type") == "local"), None)
        if local_first:
            current_model = local_first["id"]
            current_model_name = local_first["name"]
        else:
            current_model = models[0]["id"]
            current_model_name = models[0]["name"]
    
    # Initialize key store and components with selected model
    key_store = KeyStore()
    ai_client = AIClient(current_model, key_store)
    task_planner = TaskPlanner(ai_client)
    project_state = ProjectState()
    step_executor = StepExecutor(ai_client, project_state)
    active_project_task = None
    
    # Show current model
    console.print(f"\n[dim]Current Model: {current_model_name}[/dim]")
    console.print(f"[dim]Type \\ to open model/key menu[/dim]")
    
    # Main interaction loop
    while True:
        console.print()

        # Cleanup finished background task
        if active_project_task and active_project_task.done():
            active_project_task = None
        
        # Display project name in prompt if active
        if step_executor.current_project_name:
            console.print(f"[bold #C8A882]{step_executor.current_project_name} User:[/bold #C8A882]", end=" ")
        else:
            console.print("[bold #C8A882]User:[/bold #C8A882]", end=" ")
        
        user_input = Prompt.ask("", console=console)
        
        if user_input.lower() in ['quit', 'exit', 'q']:
            console.print("[#C8A882]Goodbye![/#C8A882]")
            break
        
        if not user_input.strip():
            continue

        # Stop/Abort running project
        if user_input.lower() in ['stop', 'abort']:
            if active_project_task and not active_project_task.done():
                # Request stop and cancel the task
                step_executor.request_stop()
                try:
                    await active_project_task
                except asyncio.CancelledError:
                    pass
                active_project_task = None
                # Also stop any background processes
                try:
                    res = await execute_safe_command_async("stop_all_processes")
                    if res.get("success"):
                        console.print(f"[dim]Stopped {res.get('count', 0)} background processes.[/dim]")
                except Exception:
                    pass
                console.print("[bold yellow]Process stopped by user. Project state saved.[/bold yellow]")
            else:
                console.print("[dim]No running project to stop.[/dim]")
            continue
        
        # Check if user wants to change model
        if user_input.strip() == '\\':
            # Open selection menu: list models or enter user API key
            new_model = select_model(key_store, current_model)
            current_model = new_model
            
            # Get model name for display
            for model in models:
                if model["id"] == current_model:
                    current_model_name = model["name"]
                    break
            
            # Reinitialize AI client with new model (and keep key_store)
            ai_client = AIClient(current_model, key_store)
            task_planner = TaskPlanner(ai_client)
            step_executor = StepExecutor(ai_client, project_state)
            
            console.print(f"[green]✓ Model/anahtar güncellendi! Kullanılan model: {current_model_name}[/green]")
            continue
        
        # Handle project management commands
        if user_input.lower() == 'list':
            projects = project_state.list_projects()
            if not projects:
                console.print("[#C8A882]No saved projects found.[/#C8A882]")
            else:
                table = Table(title="Saved Projects", border_style="#C8A882")
                table.add_column("ID", style="#C8A882")
                table.add_column("Name", style="green")
                table.add_column("Status", style="yellow")
                table.add_column("Progress", style="blue")
                table.add_column("Substeps", style="magenta")
                table.add_column("Created", style="dim")
                
                for proj in projects:
                    table.add_row(
                        proj["id"],
                        proj["name"],
                        proj["status"],
                        f"{proj['current_step']}/{proj['total_steps']}",
                        proj.get("subprogress", "-"),
                        proj["created"]
                    )
                console.print(table)
            continue
        
        if user_input.lower().startswith('resume '):
            project_id = user_input[7:].strip()
            saved_project = project_state.load_project(project_id)
            if not saved_project:
                console.print(f"[red]Project '{project_id}' not found.[/red]")
            else:
                if active_project_task and not active_project_task.done():
                    console.print("[yellow]A project is already running. Type 'stop' to abort it before resuming another.[/yellow]")
                else:
                    active_project_task = asyncio.create_task(step_executor.execute_complex_task(
                        saved_project["task_name"],
                        saved_project["steps"],
                        saved_project["original_input"],
                        project_id=project_id
                    ))
                    console.print("[dim]Resumed project. Type 'stop' to abort.[/dim]")
            continue
        
        if user_input.lower().startswith('delete '):
            project_id = user_input[7:].strip()
            if project_state.load_project(project_id):
                confirm = Confirm.ask(f"[#C8A882]Delete project '{project_id}'?[/#C8A882]")
                if confirm:
                    project_state.delete_project(project_id)
                    console.print(f"[green]Project '{project_id}' deleted.[/green]")
            else:
                console.print(f"[red]Project '{project_id}' not found.[/red]")
            continue

        # Process management commands
        if user_input.lower() == 'ps':
            try:
                res = await execute_safe_command_async("list_processes")
                if not res.get("success"):
                    console.print(f"[red]Process list error: {res.get('error')}[/red]")
                else:
                    procs = res.get("processes", [])
                    if not procs:
                        console.print("[dim]No active processes.[/dim]")
                    else:
                        table = Table(title="Active Processes", border_style="#C8A882")
                        table.add_column("PID", style="#C8A882")
                        table.add_column("Command", style="green")
                        table.add_column("CWD", style="blue")
                        table.add_column("Started", style="dim")
                        table.add_column("Status", style="yellow")
                        table.add_column("Addresses", style="magenta")
                        for p in procs:
                            addrs = p.get("addresses") or []
                            table.add_row(
                                str(p.get("pid")),
                                p.get("command", "-"),
                                p.get("cwd", "-"),
                                p.get("started_at", "-"),
                                p.get("status", "-"),
                                ", ".join(addrs) if addrs else "-",
                            )
                        console.print(table)
            except Exception as e:
                console.print(f"[red]ps failed: {e}[/red]")
            continue

        if user_input.lower().startswith('logs '):
            parts = user_input.split()
            pid = parts[1] if len(parts) > 1 else None
            n = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 200
            if not pid:
                console.print("[yellow]Usage: logs <pid> [n][/yellow]")
            else:
                try:
                    res = await execute_safe_command_async("tail_logs", pid=str(pid), n=n)
                    if not res.get("success"):
                        console.print(f"[red]Logs error: {res.get('error')}[/red]")
                    else:
                        lines = res.get("lines", [])
                        out = "".join(lines)
                        console.print(Panel(Markdown(f"```\n{out}\n```"), title=f"[bold #C8A882]Logs PID {pid}[/bold #C8A882]", border_style="#C8A882"))
                except Exception as e:
                    console.print(f"[red]Logs failed: {e}[/red]")
            continue

        if user_input.lower().startswith('launch '):
            proj_id = user_input[7:].strip()
            saved = project_state.load_project(proj_id)
            if not saved:
                console.print(f"[red]Project '{proj_id}' not found.[/red]")
            else:
                # Determine workspace
                ws = saved.get("workspace")
                if not ws:
                    ws = str((BASE_DIR / "Workspace" / proj_id).resolve())
                try:
                    res = await execute_safe_command_async("launch_auto", cwd=ws)
                    if res.get("success"):
                        addrs = res.get("addresses") or []
                        addr = addrs[0] if addrs else "(address pending)"
                        console.print(f"[green]✓ Launched '{proj_id}' at {addr} (pid {res.get('pid')})[/green]")
                    else:
                        console.print(f"[yellow]Launch failed: {res.get('error')}[/yellow]")
                except Exception as e:
                    console.print(f"[red]Launch error: {e}[/red]")
            continue

        if user_input.lower().startswith('kill '):
            pid = user_input[5:].strip()
            try:
                res = await execute_safe_command_async("stop_process", pid=str(pid))
                if res.get("success"):
                    console.print(f"[green]✓ Process {pid} stopped[/green]")
                else:
                    console.print(f"[yellow]Stop failed: {res.get('error')}[/yellow]")
            except Exception as e:
                console.print(f"[red]Stop error: {e}[/red]")
            continue

        if user_input.lower().startswith('restart '):
            pid = user_input[8:].strip()
            try:
                res = await execute_safe_command_async("restart_process", pid=str(pid))
                if res.get("success"):
                    console.print(f"[green]✓ Process {pid} restarted (new pid {res.get('pid')})[/green]")
                else:
                    console.print(f"[yellow]Restart failed: {res.get('error')}[/yellow]")
            except Exception as e:
                console.print(f"[red]Restart error: {e}[/red]")
            continue

        if user_input.lower() == 'stop-all':
            try:
                res = await execute_safe_command_async("stop_all_processes")
                if res.get("success"):
                    console.print(f"[green]✓ Stopped {res.get('count', 0)} processes[/green]")
                else:
                    console.print(f"[yellow]Stop-all failed: {res.get('error')}[/yellow]")
            except Exception as e:
                console.print(f"[red]Stop-all error: {e}[/red]")
            continue

        if user_input.lower().startswith('runbg '):
            cmd = user_input[6:].strip()
            try:
                res = await execute_safe_command_async("run_command_bg", command=cmd, cwd=str(Path.cwd()))
                if res.get("success"):
                    console.print(f"[green]✓ Started '{cmd}' (pid {res.get('pid')})[/green]")
                else:
                    console.print(f"[yellow]Background start failed: {res.get('error')}[/yellow]")
            except Exception as e:
                console.print(f"[red]Background run error: {e}[/red]")
            continue
        
        # Analyze task mode
        console.print()
        analysis = await task_planner.analyze_task(user_input)
        
        # Execute based on mode
        if analysis.get("mode") == "project" and analysis.get("steps"):
            # Project mode: step-by-step execution for both small and large tasks
            if active_project_task and not active_project_task.done():
                console.print("[yellow]A project is already running. Type 'stop' to abort it before starting a new one.[/yellow]")
            else:
                active_project_task = asyncio.create_task(
                    step_executor.execute_complex_task(
                        analysis.get("task_name") or "Project",
                        analysis["steps"],
                        user_input,
                        complexity_hint=analysis.get("complexity")
                    )
                )
                console.print("[dim]Project started. Type 'stop' to abort.[/dim]")
        else:
            # Conversation mode: quick direct response
            await step_executor.execute_simple_task(user_input)


if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user. Goodbye![/yellow]")
        sys.exit(0)
