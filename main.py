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
from commands import execute_safe_command

# Console setup
console = Console()

# Load configuration
CONFIG = get_config()
if not validate_config(CONFIG):
    console.print("[bold red]Error: AI_API_KEY environment variable not set![/bold red]")
    console.print("[yellow]Please configure the API key in Replit Secrets.[/yellow]")
    sys.exit(1)

# Extract configuration
API_KEY = CONFIG["api_key"]
MODEL = CONFIG["model"]
API_ENDPOINT = CONFIG["api_endpoint"]


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
                    projects.append({
                        "id": project_file.stem,
                        "name": data.get("task_name", "Unknown"),
                        "created": data.get("created_at", "Unknown"),
                        "status": data.get("status", "Unknown"),
                        "current_step": data.get("current_step", 0),
                        "total_steps": len(data.get("steps", []))
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


class AIClient:
    """Handles communication with the AI API"""
    
    def __init__(self):
        self.api_key = API_KEY
        self.model = MODEL
        self.endpoint = API_ENDPOINT
    
    async def send_message(self, messages: List[Dict], temperature: float = 0.7) -> str:
        """Send a message to the AI and get a response"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
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
            console.print(f"[red]API Error: {e}[/red]")
            return ""
        except Exception as e:
            console.print(f"[red]Unexpected error: {e}[/red]")
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
- Building applications or systems
- Multi-step technical tasks
- Code development or refactoring
- File system operations

User Input: {user_input}

If this is CATEGORY 2 (project work), break it into 3-10 logical steps.

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
            
            return json.loads(response)
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
    
    async def execute_simple_task(self, user_input: str):
        """Execute a simple conversation/question directly"""
        messages = [
            {"role": "system", "content": "You are a helpful AI assistant named Oroto AI."},
            {"role": "user", "content": user_input}
        ]
        
        with Progress(
            SpinnerColumn(spinner_name="dots", style="#C8A882"),
            TextColumn("[#C8A882]Thinking...[/#C8A882]"),
            console=console
        ) as progress:
            progress.add_task(description="", total=None)
            response = await self.ai_client.send_message(messages)
        
        if response:
            console.print(Panel(Markdown(response), title="[bold #C8A882]AI[/bold #C8A882]", border_style="#C8A882"))
    
    async def execute_complex_task(self, task_name: str, steps: List[str], original_input: str, project_id: Optional[str] = None):
        """Execute a complex task step by step with save/resume capability"""
        from thinking_python import prevent_hallucination_in_long_tasks, create_version_snapshot
        
        # Generate project ID if not resuming
        if not project_id:
            project_id = f"project_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Try to load existing project state
        saved_state = self.project_state.load_project(project_id)
        if saved_state:
            context = saved_state.get("context", "")
            results = saved_state.get("results", [])
            start_step = saved_state.get("current_step", 0)
            permission_granted = saved_state.get("permission_granted", False)
            console.print(f"[green]Resuming project: {task_name} from step {start_step + 1}[/green]")
        else:
            context = f"Original Task: {original_input}\n\nTask Breakdown:\n"
            for i, step in enumerate(steps, 1):
                context += f"{i}. {step}\n"
            results = []
            start_step = 0
            permission_granted = False
        
        console.print(Panel(
            f"[bold #C8A882]Task:[/bold #C8A882] {task_name}\n"
            f"[bold #C8A882]Project ID:[/bold #C8A882] {project_id}\n"
            f"[bold #C8A882]Total Steps:[/bold #C8A882] {len(steps)}",
            title="[bold #C8A882]Execution Plan[/bold #C8A882]",
            border_style="#C8A882"
        ))
        
        # Display steps
        console.print("\n[bold #C8A882]Steps to execute:[/bold #C8A882]")
        for i, step in enumerate(steps, 1):
            status = "✓" if i <= start_step else "○"
            console.print(f"  {status} {i}. {step}")
        console.print()
        
        # ONE-TIME PERMISSION: Ask only if not already granted
        if not permission_granted and start_step == 0:
            console.print(Panel(
                "[bold #C8A882]Permission Required[/bold #C8A882]\n\n"
                "This task will execute all steps automatically.\n"
                "Files may be created, modified, or updated as needed.\n\n"
                "Do you want to proceed with automatic execution?",
                border_style="#C8A882"
            ))
            
            permission_granted = Confirm.ask(
                "[#C8A882]Grant permission to proceed?[/#C8A882]",
                default=True
            )
            
            if not permission_granted:
                console.print("[yellow]Task cancelled by user.[/yellow]")
                return
            
            console.print("[green]✓ Permission granted. Executing all steps automatically...[/green]\n")
        
        for i, step in enumerate(steps, 1):
            # Skip completed steps
            if i <= start_step:
                continue
                
            console.print(f"\n[bold #C8A882]═══ Step {i}/{len(steps)}: {step} ═══[/bold #C8A882]\n")
            
            # Prevent hallucination by trimming context for long tasks
            trimmed_context = prevent_hallucination_in_long_tasks(context)
            
            # Build step prompt with context
            step_prompt = f"{trimmed_context}\n\nPrevious steps completed:\n"
            for j, prev_result in enumerate(results, 1):
                step_prompt += f"\nStep {j} Result:\n{prev_result}\n"
            
            step_prompt += f"\n\nNow execute Step {i}: {step}\n\nProvide a detailed response for this step."
            
            # Enhanced system prompt with file operation guidance
            system_prompt = """You are Oroto AI, executing a multi-step task.

IMPORTANT GUIDELINES:
1. For NEW projects: Describe the complete file and folder structure to create, with exact file contents
2. For UPDATES: Identify the specific code section to change and provide the exact replacement
3. Be precise and avoid generating unnecessary content or hallucinations
4. Focus on the current step while being aware of previous progress
5. Clearly report any errors that occur
6. Provide a brief summary of what was accomplished in this step
7. Version snapshots are automatically created after each step for rollback capability

When creating projects, provide clear structure like:
Project: my_app/
- index.html: [full HTML content]
- styles.css: [full CSS content]
- script.js: [full JavaScript content]

When updating code, specify:
- File: path/to/file.py
- Find: [exact code to replace]
- Replace with: [new code]"""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": step_prompt}
            ]
            
            with Progress(
                SpinnerColumn(spinner_name="dots", style="#C8A882"),
                TextColumn("[#C8A882]Thinking...[/#C8A882]"),
                console=console
            ) as progress:
                progress.add_task(description="", total=None)
                response = await self.ai_client.send_message(messages)
            
            if response:
                console.print(Panel(Markdown(response), title=f"[bold #C8A882]AI - Step {i}[/bold #C8A882]", border_style="#C8A882"))
                results.append(response)
                
                # Create version snapshot for this step
                # Collect files that might have been modified in this project directory
                files_to_snapshot = []
                try:
                    # Snapshot all files in current directory (excluding hidden and system dirs)
                    for file in Path.cwd().rglob("*"):
                        if file.is_file() and not any(part.startswith(".") for part in file.parts):
                            try:
                                files_to_snapshot.append(str(file.relative_to(Path.cwd())))
                            except ValueError:
                                pass  # Skip files outside cwd
                    
                    if files_to_snapshot:
                        snapshot_result = create_version_snapshot(project_id, i, files_to_snapshot)
                        if snapshot_result["success"]:
                            console.print(f"[dim]✓ Version snapshot created: {snapshot_result['snapshot_id']}[/dim]")
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not create version snapshot: {str(e)}[/yellow]")
                
                # Save progress with permission status
                project_data = {
                    "project_id": project_id,
                    "task_name": task_name,
                    "original_input": original_input,
                    "steps": steps,
                    "current_step": i,
                    "results": results,
                    "context": context,
                    "permission_granted": permission_granted,
                    "status": "completed" if i == len(steps) else "in_progress",
                    "created_at": saved_state.get("created_at", datetime.now().isoformat()) if saved_state else datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat()
                }
                self.project_state.save_project(project_id, project_data)
                
                # AUTOMATIC EXECUTION: No confirmation prompts between steps
                if i < len(steps):
                    console.print(f"\n[dim]→ Proceeding to step {i + 1}...[/dim]")
        
        # Final summary
        console.print(f"\n[bold green]✓ All steps completed successfully![/bold green]")
        console.print(Panel(
            f"[bold #C8A882]Task Summary[/bold #C8A882]\n\n"
            f"Project: {task_name}\n"
            f"Total Steps: {len(steps)}\n"
            f"Project ID: {project_id}\n"
            f"Status: ✓ Completed",
            border_style="green"
        ))


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
        "[dim]Commands: list | resume <id> | delete <id> | quit[/dim]",
        border_style="#C8A882",
        title="[bold #C8A882]Welcome[/bold #C8A882]"
    ))
    
    # Initialize components
    ai_client = AIClient()
    task_planner = TaskPlanner(ai_client)
    project_state = ProjectState()
    step_executor = StepExecutor(ai_client, project_state)
    
    # Main interaction loop
    while True:
        console.print()
        console.print("[bold #C8A882]User:[/bold #C8A882]", end=" ")
        user_input = Prompt.ask("", console=console)
        
        if user_input.lower() in ['quit', 'exit', 'q']:
            console.print("[#C8A882]Goodbye![/#C8A882]")
            break
        
        if not user_input.strip():
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
                table.add_column("Created", style="dim")
                
                for proj in projects:
                    table.add_row(
                        proj["id"],
                        proj["name"],
                        proj["status"],
                        f"{proj['current_step']}/{proj['total_steps']}",
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
                await step_executor.execute_complex_task(
                    saved_project["task_name"],
                    saved_project["steps"],
                    saved_project["original_input"],
                    project_id=project_id
                )
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
        
        # Analyze task mode
        console.print()
        analysis = await task_planner.analyze_task(user_input)
        
        # Execute based on mode
        if analysis.get("mode") == "project" and analysis.get("is_complex") and analysis.get("steps"):
            # Project mode: step-by-step execution
            await step_executor.execute_complex_task(
                analysis["task_name"],
                analysis["steps"],
                user_input
            )
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
