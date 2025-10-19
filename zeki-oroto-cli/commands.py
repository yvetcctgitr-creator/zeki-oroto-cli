"""
Oroto AI Command Execution Module
Safe, predefined functions for project operations
"""

import os
import json
import asyncio
from datetime import datetime
from asyncio.subprocess import PIPE
from pathlib import Path
from typing import Dict, List, Optional, Any
import shutil

from thinking_python import validate_file_path
from process_manager import (
    start_process,
    stop_process,
    restart_process,
    list_processes,
    tail_logs,
    launch_auto,
    stop_all_processes,
)


def list_directory(path: str = ".") -> Dict:
    """
    List all files and folders in a directory.
    
    Args:
        path: Directory path to list (default: current directory)
    
    Returns:
        Dictionary with files and folders
    """
    result = {
        "success": False,
        "path": path,
        "files": [],
        "folders": [],
        "error": None
    }
    
    try:
        target_path = Path(path).resolve()
        
        # Security: ensure path is within current working directory
        try:
            target_path.relative_to(Path.cwd().resolve())
        except ValueError:
            result["error"] = "Access denied: Path outside project directory"
            return result
        
        if not target_path.exists():
            result["error"] = f"Path not found: {path}"
            return result
        
        if not target_path.is_dir():
            result["error"] = f"Not a directory: {path}"
            return result
        
        # List contents
        for item in target_path.iterdir():
            if item.is_file():
                result["files"].append({
                    "name": item.name,
                    "size": item.stat().st_size,
                    "path": str(item.relative_to(Path.cwd()))
                })
            elif item.is_dir():
                result["folders"].append({
                    "name": item.name,
                    "path": str(item.relative_to(Path.cwd()))
                })
        
        result["success"] = True
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def read_file(file_path: str, max_lines: Optional[int] = None) -> Dict:
    """
    Read the contents of a file.
    
    Args:
        file_path: Path to the file
        max_lines: Maximum number of lines to read (optional)
    
    Returns:
        Dictionary with file content
    """
    result = {
        "success": False,
        "file": file_path,
        "content": None,
        "lines": 0,
        "truncated": False,
        "error": None
    }
    
    try:
        target_path = Path(file_path).resolve()
        
        # Security: ensure path is within current working directory
        try:
            target_path.relative_to(Path.cwd().resolve())
        except ValueError:
            result["error"] = "Access denied: Path outside project directory"
            return result
        
        if not target_path.exists():
            result["error"] = f"File not found: {file_path}"
            return result
        
        if not target_path.is_file():
            result["error"] = f"Not a file: {file_path}"
            return result
        
        # Read file
        with open(target_path, 'r', encoding='utf-8', errors='ignore') as f:
            if max_lines:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        result["truncated"] = True
                        break
                    lines.append(line.rstrip('\n'))
                result["content"] = '\n'.join(lines)
            else:
                result["content"] = f.read()
        
        result["lines"] = len(result["content"].split('\n'))
        result["success"] = True
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def write_file(file_path: str, content: str, create_dirs: bool = True) -> Dict:
    """
    Write content to a file.
    
    Args:
        file_path: Path to the file
        content: Content to write
        create_dirs: Create parent directories if they don't exist
    
    Returns:
        Dictionary with operation result
    """
    result = {
        "success": False,
        "file": file_path,
        "bytes_written": 0,
        "error": None
    }
    
    try:
        target_path = Path(file_path).resolve()
        
        # Security: ensure path is within current working directory
        try:
            target_path.relative_to(Path.cwd().resolve())
        except ValueError:
            result["error"] = "Access denied: Path outside project directory"
            return result
        
        # Create parent directories if needed
        if create_dirs:
            target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write file
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        result["bytes_written"] = len(content.encode('utf-8'))
        result["success"] = True
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def create_empty_file(file_path: str, create_dirs: bool = True) -> Dict:
    """
    Explicitly create an empty file before writing content.
    Ensures parent folders exist and prevents path traversal.
    
    Args:
        file_path: Path to the file to create
        create_dirs: Whether to create parent directories
    
    Returns:
        Result dict with success and whether it already existed
    """
    result = {
        "success": False,
        "file": file_path,
        "already_exists": False,
        "error": None
    }
    try:
        target_path = Path(file_path).resolve()
        # Security: ensure path is within current working directory
        try:
            target_path.relative_to(Path.cwd().resolve())
        except ValueError:
            result["error"] = "Access denied: Path outside project directory"
            return result
        # Ensure parent folder
        if create_dirs:
            target_path.parent.mkdir(parents=True, exist_ok=True)
        # Create file atomically
        if target_path.exists():
            result["already_exists"] = True
            result["success"] = True
            return result
        with open(target_path, 'x', encoding='utf-8') as f:
            f.write("")
        result["success"] = True
    except FileExistsError:
        result["already_exists"] = True
        result["success"] = True
    except Exception as e:
        result["error"] = str(e)
    return result


def delete_file(file_path: str) -> Dict:
    """
    Safely delete a file within the current working directory.
    """
    result = {"success": False, "file": file_path, "error": None}
    try:
        target_path = Path(file_path).resolve()
        try:
            target_path.relative_to(Path.cwd().resolve())
        except ValueError:
            result["error"] = "Access denied: Path outside project directory"
            return result
        if not target_path.exists():
            result["error"] = f"File not found: {file_path}"
            return result
        if not target_path.is_file():
            result["error"] = f"Not a file: {file_path}"
            return result
        target_path.unlink()
        result["success"] = True
    except Exception as e:
        result["error"] = str(e)
    return result


def delete_folder(folder_path: str, recursive: bool = False) -> Dict:
    """
    Safely delete a folder. If recursive is True, delete contents.
    """
    result = {"success": False, "folder": folder_path, "error": None}
    try:
        target_path = Path(folder_path).resolve()
        try:
            target_path.relative_to(Path.cwd().resolve())
        except ValueError:
            result["error"] = "Access denied: Path outside project directory"
            return result
        if not target_path.exists():
            result["error"] = f"Folder not found: {folder_path}"
            return result
        if not target_path.is_dir():
            result["error"] = f"Not a folder: {folder_path}"
            return result
        if recursive:
            shutil.rmtree(target_path)
        else:
            target_path.rmdir()
        result["success"] = True
    except Exception as e:
        result["error"] = str(e)
    return result


def create_folder(folder_path: str) -> Dict:
    """
    Create a new folder (and parent folders if needed).
    
    Args:
        folder_path: Path to the folder to create
    
    Returns:
        Dictionary with operation result
    """
    result = {
        "success": False,
        "folder": folder_path,
        "already_exists": False,
        "error": None
    }
    
    try:
        target_path = Path(folder_path).resolve()
        
        # Security: ensure path is within current working directory
        try:
            target_path.relative_to(Path.cwd().resolve())
        except ValueError:
            result["error"] = "Access denied: Path outside project directory"
            return result
        
        if target_path.exists():
            result["already_exists"] = True
            result["success"] = True
            return result
        
        # Create folder
        target_path.mkdir(parents=True, exist_ok=True)
        result["success"] = True
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def create_project_structure(project_name: str, structure: Dict[str, Any]) -> Dict:
    """
    Create a new project structure.
    
    Args:
        project_name: Name of the project
        structure: Project structure as a dictionary
    
    Returns:
        Dictionary with operation result
    """
    result = {
        "success": False,
        "project_name": project_name,
        "structure": structure,
        "error": None
    }
    
    try:
        project_path = Path.cwd() / project_name
        project_path.mkdir(parents=True, exist_ok=True)
        
        for folder_name, contents in structure.items():
            folder_path = project_path / folder_name
            folder_path.mkdir(parents=True, exist_ok=True)
            
            if isinstance(contents, dict):
                for file_name, file_content in contents.items():
                    file_path = folder_path / file_name
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(str(file_content))
    
        result["success"] = True
    except Exception as e:
        result["error"] = str(e)
    
    return result


def get_project_structure(path: str = ".", max_depth: int = 3) -> Dict:
    """
    Get a tree structure of the project.
    
    Args:
        path: Root path to analyze
        max_depth: Maximum depth to traverse
    
    Returns:
        Dictionary with project structure
    """
    result = {
        "success": False,
        "structure": {},
        "total_files": 0,
        "total_folders": 0,
        "error": None
    }
    
    def build_tree(current_path: Path, depth: int) -> Dict:
        if depth > max_depth:
            return {"truncated": True}
        
        tree = {}
        try:
            for item in sorted(current_path.iterdir()):
                # Skip hidden files/folders
                if item.name.startswith('.'):
                    continue
                
                if item.is_file():
                    tree[item.name] = {
                        "type": "file",
                        "size": item.stat().st_size
                    }
                    result["total_files"] += 1
                elif item.is_dir():
                    tree[item.name] = {
                        "type": "folder",
                        "contents": build_tree(item, depth + 1)
                    }
                    result["total_folders"] += 1
        except PermissionError:
            pass
        
        return tree
    
    try:
        target_path = Path(path).resolve()
        
        # Security: ensure path is within current working directory
        try:
            target_path.relative_to(Path.cwd().resolve())
        except ValueError:
            result["error"] = "Access denied: Path outside project directory"
            return result
        
        result["structure"] = build_tree(target_path, 0)
        result["success"] = True
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def search_in_files(search_term: str, file_pattern: str = "*.py", max_results: int = 50) -> Dict:
    """
    Search for a term in files matching a pattern.
    
    Args:
        search_term: Text to search for
        file_pattern: File pattern to match (e.g., "*.py", "*.txt")
        max_results: Maximum number of results to return
    
    Returns:
        Dictionary with search results
    """
    result = {
        "success": False,
        "search_term": search_term,
        "pattern": file_pattern,
        "matches": [],
        "total_matches": 0,
        "truncated": False,
        "error": None
    }
    
    try:
        cwd = Path.cwd()
        matches_found = 0
        
        for file_path in cwd.rglob(file_pattern):
            if not file_path.is_file():
                continue
            
            # Skip hidden files
            if any(part.startswith('.') for part in file_path.parts):
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        if search_term in line:
                            matches_found += 1
                            if matches_found <= max_results:
                                result["matches"].append({
                                    "file": str(file_path.relative_to(cwd)),
                                    "line": line_num,
                                    "content": line.strip()
                                })
                            else:
                                result["truncated"] = True
            except Exception:
                pass
        
        result["total_matches"] = matches_found
        result["success"] = True
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def create_carousel_project(carousel_name: str, files: Dict[str, str], include_index: bool = True) -> Dict:
    """
    Create a folder representing a carousel with associated files and optional UI assets.
    """

    result: Dict[str, Any] = {
        "success": False,
        "carousel_root": carousel_name,
        "created_files": [],
        "errors": []
    }

    try:
        if not validate_file_path(carousel_name):
            result["errors"].append(f"Invalid carousel name: {carousel_name}")
            return result

        root_path = Path(carousel_name).resolve()
        try:
            root_path.relative_to(Path.cwd().resolve())
        except ValueError:
            result["errors"].append(f"Carousel path outside working directory: {carousel_name}")
            return result

        root_path.mkdir(exist_ok=True)

        for relative_path, content in files.items():
            if not isinstance(relative_path, str):
                result["errors"].append("File path keys must be strings")
                continue

            if ".." in relative_path or relative_path.startswith(("/", "\\")):
                result["errors"].append(f"Unsafe file path: {relative_path}")
                continue

            destination = root_path / relative_path
            try:
                destination.resolve().relative_to(root_path)
            except ValueError:
                result["errors"].append(f"Path traversal blocked: {relative_path}")
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(destination, "w", encoding="utf-8") as f:
                    f.write(str(content))
                result["created_files"].append(str(destination))
            except Exception as e:
                result["errors"].append(f"Failed to create {relative_path}: {str(e)}")

        if include_index:
            file_cards = []
            for relative_path in files.keys():
                safe_name = os.path.basename(relative_path)
                file_cards.append(f"<div class='carousel-item'><pre>{safe_name}</pre></div>")

            carousel_markup = "\n".join(file_cards) if file_cards else "<div class='carousel-item'><pre>No files yet</pre></div>"

            index_html = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\" />
    <title>{carousel_name} Carousel</title>
    <link rel=\"stylesheet\" href=\"carousel.css\" />
</head>
<body>
    <div class=\"carousel-container\">
        <button class=\"nav prev\" data-dir=\"-1\">◀</button>
        <div class=\"carousel-track\">
            {carousel_markup}
        </div>
        <button class=\"nav next\" data-dir=\"1\">▶</button>
    </div>
    <script src=\"carousel.js\"></script>
</body>
</html>
"""

            carousel_css = """body{font-family:Arial,Helvetica,sans-serif;background:#121212;color:#f5f5f5;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}.carousel-container{display:flex;align-items:center;gap:1rem}.carousel-track{width:320px;height:200px;overflow:hidden;display:flex;scroll-behavior:smooth;border:2px solid #c8a882;border-radius:8px;background:rgba(0,0,0,0.35)}.carousel-item{min-width:320px;padding:1.5rem;display:flex;justify-content:center;align-items:center}.nav{background:#c8a882;border:none;color:#121212;font-size:1.25rem;padding:0.75rem 1rem;border-radius:4px;cursor:pointer}.nav:hover{background:#e6c9a6}.nav:active{transform:scale(0.95)}pre{margin:0;font-size:1rem;white-space:pre-wrap}
"""

            carousel_js = """const track=document.querySelector('.carousel-track');const buttons=document.querySelectorAll('.nav');let index=0;const move=(dir)=>{const items=track.children;if(!items.length)return;index=(index+dir+items.length)%items.length;track.scrollTo({left:index*items[0].offsetWidth,behavior:'smooth'});};buttons.forEach(btn=>btn.addEventListener('click',()=>move(parseInt(btn.dataset.dir,10))));
"""

            index_path = root_path / "index.html"
            css_path = root_path / "carousel.css"
            js_path = root_path / "carousel.js"

            with open(index_path, "w", encoding="utf-8") as f:
                f.write(index_html)
            with open(css_path, "w", encoding="utf-8") as f:
                f.write(carousel_css)
            with open(js_path, "w", encoding="utf-8") as f:
                f.write(carousel_js)

            result["created_files"].extend([
                str(index_path),
                str(css_path),
                str(js_path)
            ])

        result["success"] = not result["errors"]
    except Exception as e:
        result["errors"].append(str(e))

    return result


def execute_safe_command(command_name: str, **kwargs) -> Dict:
    """
    Execute a safe, predefined command.
    
    Args:
        command_name: Name of the command to execute
        **kwargs: Arguments for the command
    
    Returns:
        Dictionary with command result
    """
    commands = {
        "list_directory": list_directory,
        "read_file": read_file,
        "write_file": write_file,
        "create_folder": create_folder,
        "create_project_structure": create_project_structure,
        "get_project_structure": get_project_structure,
        "search_in_files": search_in_files,
        "create_carousel_project": create_carousel_project,
        "create_empty_file": create_empty_file,
        "delete_file": delete_file,
        "delete_folder": delete_folder
    }
    
    if command_name not in commands:
        return {
            "success": False,
            "error": f"Unknown command: {command_name}",
            "available_commands": list(commands.keys())
        }
    
    try:
        return commands[command_name](**kwargs)
    except Exception as e:
        return {
            "success": False,
            "error": f"Command execution failed: {str(e)}"
        }


# Example usage demonstrations
if __name__ == "__main__":
    print("=== Oroto AI Command Module ===\n")
    
    # Example 1: List current directory
    print("1. Listing current directory:")
    result = list_directory(".")
    print(json.dumps(result, indent=2))
    
    # Example 2: Get project structure
    print("\n2. Getting project structure:")
    result = get_project_structure(".", max_depth=2)
    print(json.dumps(result, indent=2))
    
    # Example 3: Execute safe command
    print("\n3. Executing safe command:")
    result = execute_safe_command("list_directory", path=".")
    print(json.dumps(result, indent=2))

def _is_command_allowed(cmd: str) -> bool:
    """Basic allowlist to prevent destructive shell commands."""
    cmd = cmd.strip().lower()
    if not cmd:
        return False
    allowed_prefixes = [
        "npm", "pnpm", "yarn", "npx", "pytest", "pip", "python",
        "node", "serve", "http-server"
    ]
    first = cmd.split()[0]
    return any(first == p or first.startswith(p) for p in allowed_prefixes)

async def run_command_async(command: str, cwd: Optional[str] = None, timeout: Optional[int] = None, env: Optional[Dict[str, str]] = None) -> Dict:
    """
    Run a shell command safely and allow interruption via asyncio cancellation.

    Args:
        command: The shell command to execute (single-line).
        cwd: Working directory (must be within current project path).
        timeout: Optional timeout in seconds.
        env: Optional environment overrides.

    Returns:
        Dictionary with execution result and logs.
    """
    result = {
        "success": False,
        "command": command,
        "cwd": cwd or str(Path.cwd()),
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "error": None,
        "cancelled": False,
        "started_at": datetime.now().isoformat(),
        "ended_at": None,
        "log_path": None,
        "error_class": None,
    }

    def _classify_error(stderr: str, exit_code: Optional[int]) -> str:
        s = (stderr or "").lower()
        if "permission denied" in s or "access is denied" in s:
            return "permission"
        if "address already in use" in s or "port" in s and "in use" in s:
            return "port_in_use"
        if "module not found" in s or "cannot import" in s or "no module named" in s:
            return "missing_dependency"
        if "assert" in s or "failed" in s and "test" in s:
            return "test_failure"
        if "syntaxerror" in s or "traceback" in s and exit_code:
            return "runtime_error"
        if exit_code:
            return "error"
        return "unknown"

    try:
        if not _is_command_allowed(command):
            result["error"] = "Command not allowed. Only test/build/dev commands are permitted."
            return result

        # Resolve and validate cwd within project
        workdir = Path(cwd).resolve() if cwd else Path.cwd().resolve()
        try:
            workdir.relative_to(Path.cwd().resolve())
        except ValueError:
            result["error"] = "Access denied: cwd outside project directory"
            return result
        if not workdir.exists() or not workdir.is_dir():
            result["error"] = f"Invalid cwd: {workdir}"
            return result

        # Prepare logs directory
        logs_dir = workdir / ".logs"
        try:
            logs_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        log_file = logs_dir / f"cmd-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
        result["log_path"] = str(log_file)

        # Prepare environment
        run_env = os.environ.copy()
        if env:
            for k, v in env.items():
                if isinstance(k, str) and isinstance(v, str):
                    run_env[k] = v

        # Start subprocess (shell for convenience)
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(workdir),
            stdout=PIPE,
            stderr=PIPE,
            env=run_env
        )

        async def _read_stream(stream, buf):
            try:
                while True:
                    chunk = await stream.read(1024)
                    if not chunk:
                        break
                    buf.append(chunk.decode(errors='ignore'))
            except Exception:
                # Swallow stream read errors
                pass

        stdout_buf = []
        stderr_buf = []
        read_out = asyncio.create_task(_read_stream(proc.stdout, stdout_buf))
        read_err = asyncio.create_task(_read_stream(proc.stderr, stderr_buf))

        try:
            if timeout:
                await asyncio.wait_for(proc.wait(), timeout=timeout)
            else:
                await proc.wait()
            await asyncio.gather(read_out, read_err)
            result["exit_code"] = proc.returncode
            result["stdout"] = ''.join(stdout_buf)
            result["stderr"] = ''.join(stderr_buf)
            result["error_class"] = _classify_error(result["stderr"], result["exit_code"])
            result["success"] = proc.returncode == 0
            # Write log file
            try:
                with open(log_file, "w", encoding="utf-8", errors="ignore") as f:
                    f.write(f"$ {command}\n")
                    f.write(f"started_at={result['started_at']} ended_at={datetime.now().isoformat()} exit_code={proc.returncode}\n\n")
                    if result["stdout"]:
                        f.write("--- stdout ---\n")
                        f.write(result["stdout"]) 
                        f.write("\n")
                    if result["stderr"]:
                        f.write("--- stderr ---\n")
                        f.write(result["stderr"]) 
                        f.write("\n")
            except Exception:
                pass
            return result
        except asyncio.TimeoutError:
            # Timeout -> terminate
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
            await asyncio.gather(read_out, read_err, return_exceptions=True)
            result["exit_code"] = proc.returncode
            result["stdout"] = ''.join(stdout_buf)
            result["stderr"] = ''.join(stderr_buf)
            result["error"] = "Command timed out"
            result["error_class"] = _classify_error(result["stderr"], result["exit_code"])
            result["success"] = False
            # Write log file
            try:
                with open(log_file, "w", encoding="utf-8", errors="ignore") as f:
                    f.write(f"$ {command}\n")
                    f.write(f"started_at={result['started_at']} ended_at={datetime.now().isoformat()} timeout=1 exit_code={proc.returncode}\n\n")
                    if result["stdout"]:
                        f.write("--- stdout ---\n")
                        f.write(result["stdout"]) 
                        f.write("\n")
                    if result["stderr"]:
                        f.write("--- stderr ---\n")
                        f.write(result["stderr"]) 
                        f.write("\n")
            except Exception:
                pass
            return result
        except asyncio.CancelledError:
            # Cancellation -> terminate quickly and propagate
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
            await asyncio.gather(read_out, read_err, return_exceptions=True)
            result["exit_code"] = proc.returncode
            result["stdout"] = ''.join(stdout_buf)
            result["stderr"] = ''.join(stderr_buf)
            result["cancelled"] = True
            result["error_class"] = _classify_error(result["stderr"], result["exit_code"])
            result["success"] = False
            # Write log file
            try:
                with open(log_file, "w", encoding="utf-8", errors="ignore") as f:
                    f.write(f"$ {command}\n")
                    f.write(f"started_at={result['started_at']} ended_at={datetime.now().isoformat()} cancelled=1 exit_code={proc.returncode}\n\n")
                    if result["stdout"]:
                        f.write("--- stdout ---\n")
                        f.write(result["stdout"]) 
                        f.write("\n")
                    if result["stderr"]:
                        f.write("--- stderr ---\n")
                        f.write(result["stderr"]) 
                        f.write("\n")
            except Exception:
                pass
            raise
        finally:
            result["ended_at"] = datetime.now().isoformat()

    except Exception as e:
        result["error"] = str(e)
        result["ended_at"] = datetime.now().isoformat()
        # Try to write minimal log
        try:
            lp = result.get("log_path")
            if lp:
                with open(lp, "a", encoding="utf-8", errors="ignore") as f:
                    f.write(f"error: {result['error']}\n")
        except Exception:
            pass
        return result

aSYNC_COMMANDS = {
    "run_command": run_command_async,
    "run_command_bg": start_process,
    "stop_process": stop_process,
    "restart_process": restart_process,
    "list_processes": list_processes,
    "tail_logs": tail_logs,
    "launch_auto": launch_auto,
    "stop_all_processes": stop_all_processes,
}

async def execute_safe_command_async(command_name: str, **kwargs) -> Dict:
    """Async dispatcher for commands that need cancellation support."""
    if command_name not in aSYNC_COMMANDS:
        return {
            "success": False,
            "error": f"Unknown async command: {command_name}",
            "available_async": list(aSYNC_COMMANDS.keys())
        }
    try:
        return await aSYNC_COMMANDS[command_name](**kwargs)
    except asyncio.CancelledError:
        # Propagate cancellation
        raise
    except Exception as e:
        return {"success": False, "error": f"Async command failed: {str(e)}"}
