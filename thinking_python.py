"""
Thinking Python - Helper Functions for Large-Scale Operations
This file contains only functions that the AI can execute for complex, multi-step tasks.
"""

import json
from typing import List, Dict, Any, Optional
from pathlib import Path


def break_down_task(task_description: str, num_steps: int = 5) -> List[str]:
    """
    Break down a complex task into logical steps.
    
    Args:
        task_description: The main task to break down
        num_steps: Number of steps to create (default 5)
    
    Returns:
        List of step descriptions
    """
    steps = []
    if "create" in task_description.lower() or "build" in task_description.lower():
        steps.append("Plan the architecture and structure")
        steps.append("Set up the basic framework")
        steps.append("Implement core functionality")
        steps.append("Add error handling and validation")
        steps.append("Test and refine")
    elif "modify" in task_description.lower() or "update" in task_description.lower():
        steps.append("Analyze current implementation")
        steps.append("Plan the modifications")
        steps.append("Implement changes")
        steps.append("Test modifications")
        steps.append("Verify and finalize")
    else:
        steps = [f"Step {i+1}" for i in range(num_steps)]
    
    return steps[:num_steps]


def validate_file_path(file_path: str, allowed_extensions: Optional[List[str]] = None, base_dir: Optional[str] = None) -> bool:
    """
    Validate a file path for safety and correctness with strict path traversal prevention.
    
    Args:
        file_path: Path to validate
        allowed_extensions: List of allowed file extensions (e.g., ['.py', '.txt'])
        base_dir: Base directory that the path must be within (defaults to current working directory)
    
    Returns:
        True if valid, False otherwise
    """
    try:
        path = Path(file_path)
        
        # Check for obvious path traversal attempts
        if ".." in str(path):
            return False
        
        # Resolve to absolute path and check containment
        if base_dir:
            base_path = Path(base_dir).resolve()
        else:
            base_path = Path.cwd().resolve()
        
        resolved_path = (base_path / path).resolve()
        
        # Ensure resolved path is within base directory
        try:
            resolved_path.relative_to(base_path)
        except ValueError:
            return False
        
        # Check extension if specified
        if allowed_extensions:
            if path.suffix not in allowed_extensions:
                return False
        
        return True
    except Exception:
        return False


def chunk_data(data: List[Any], chunk_size: int = 100) -> List[List[Any]]:
    """
    Split large data into manageable chunks for processing.
    
    Args:
        data: List of items to chunk
        chunk_size: Size of each chunk
    
    Returns:
        List of chunks
    """
    return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]


def merge_results(results: List[Dict]) -> Dict:
    """
    Merge multiple result dictionaries into a single consolidated result.
    
    Args:
        results: List of result dictionaries
    
    Returns:
        Merged result dictionary
    """
    merged = {
        "success": all(r.get("success", False) for r in results),
        "data": [],
        "errors": [],
        "summary": {}
    }
    
    for result in results:
        if "data" in result:
            merged["data"].extend(result["data"] if isinstance(result["data"], list) else [result["data"]])
        if "errors" in result and result["errors"]:
            merged["errors"].extend(result["errors"])
    
    merged["summary"]["total_processed"] = len(results)
    merged["summary"]["successful"] = sum(1 for r in results if r.get("success", False))
    merged["summary"]["failed"] = sum(1 for r in results if not r.get("success", False))
    
    return merged


def create_backup_config(config: Dict, backup_path: str = ".backup") -> bool:
    """
    Create a backup of configuration before making changes.
    
    Args:
        config: Configuration dictionary to backup
        backup_path: Path to backup directory
    
    Returns:
        True if backup successful, False otherwise
    """
    try:
        backup_dir = Path(backup_path)
        backup_dir.mkdir(exist_ok=True)
        
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"config_backup_{timestamp}.json"
        
        with open(backup_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        return True
    except Exception:
        return False


def validate_step_completion(step_name: str, expected_outputs: List[str], actual_outputs: List[str]) -> Dict:
    """
    Validate that a step completed successfully by checking outputs.
    
    Args:
        step_name: Name of the step being validated
        expected_outputs: List of expected output indicators
        actual_outputs: List of actual outputs produced
    
    Returns:
        Validation result dictionary
    """
    result = {
        "step": step_name,
        "valid": True,
        "missing": [],
        "extra": [],
        "message": ""
    }
    
    expected_set = set(expected_outputs)
    actual_set = set(actual_outputs)
    
    result["missing"] = list(expected_set - actual_set)
    result["extra"] = list(actual_set - expected_set)
    
    if result["missing"]:
        result["valid"] = False
        result["message"] = f"Missing expected outputs: {', '.join(result['missing'])}"
    elif not result["extra"]:
        result["message"] = "Step completed successfully"
    else:
        result["message"] = "Step completed with additional outputs"
    
    return result


def estimate_task_complexity(task_description: str) -> Dict:
    """
    Estimate the complexity of a task based on keywords and structure.
    
    Args:
        task_description: Description of the task
    
    Returns:
        Complexity estimation dictionary
    """
    complexity_keywords = {
        "high": ["integrate", "deploy", "migrate", "refactor", "optimize", "scale"],
        "medium": ["create", "build", "develop", "implement", "modify"],
        "low": ["update", "fix", "change", "add", "remove"]
    }
    
    description_lower = task_description.lower()
    
    for level, keywords in complexity_keywords.items():
        if any(keyword in description_lower for keyword in keywords):
            return {
                "level": level,
                "estimated_steps": {"high": 8, "medium": 5, "low": 3}[level],
                "requires_review": level in ["high", "medium"]
            }
    
    return {
        "level": "medium",
        "estimated_steps": 5,
        "requires_review": True
    }


def sanitize_input(user_input: str, max_length: int = 10000) -> str:
    """
    Sanitize user input for safe processing.
    
    Args:
        user_input: Raw user input
        max_length: Maximum allowed length
    
    Returns:
        Sanitized input string
    """
    # Truncate if too long
    sanitized = user_input[:max_length]
    
    # Remove potentially dangerous characters/patterns
    dangerous_patterns = ["\x00", "\r\n\r\n"]
    for pattern in dangerous_patterns:
        sanitized = sanitized.replace(pattern, "")
    
    return sanitized.strip()


def create_project_structure(project_name: str, structure: Dict[str, Any]) -> Dict:
    """
    Create complete file and folder structure for a new project.
    
    Args:
        project_name: Name of the project
        structure: Dictionary defining folders and files
                  Format: {"folder_name": {"file.txt": "content", "subfolder": {...}}}
    
    Returns:
        Result dictionary with created files and any errors
    """
    result = {
        "success": True,
        "created_files": [],
        "created_folders": [],
        "errors": []
    }
    
    try:
        project_path = Path(project_name)
        
        # Validate project name
        if not validate_file_path(project_name):
            result["success"] = False
            result["errors"].append(f"Invalid project name: {project_name}")
            return result
        
        # Create project root
        project_path.mkdir(exist_ok=True)
        result["created_folders"].append(str(project_path))
        
        # Recursive function to create structure with path validation
        def create_structure_recursive(base_path: Path, structure_dict: Dict):
            for name, content in structure_dict.items():
                # Validate each path component for safety
                if ".." in name or "/" in name or "\\" in name:
                    result["errors"].append(f"Invalid path component: {name}")
                    result["success"] = False
                    continue
                
                item_path = base_path / name
                
                # Verify resolved path is within project root
                try:
                    item_path.resolve().relative_to(project_path.resolve())
                except ValueError:
                    result["errors"].append(f"Path traversal attempt blocked: {name}")
                    result["success"] = False
                    continue
                
                if isinstance(content, dict):
                    # It's a folder
                    item_path.mkdir(exist_ok=True)
                    result["created_folders"].append(str(item_path))
                    create_structure_recursive(item_path, content)
                else:
                    # It's a file
                    try:
                        with open(item_path, 'w', encoding='utf-8') as f:
                            f.write(str(content))
                        result["created_files"].append(str(item_path))
                    except Exception as e:
                        result["errors"].append(f"Error creating {item_path}: {str(e)}")
        
        create_structure_recursive(project_path, structure)
        
        if result["errors"]:
            result["success"] = False
            
    except Exception as e:
        result["success"] = False
        result["errors"].append(f"Project creation failed: {str(e)}")
    
    return result


def update_code_section(file_path: str, old_code: str, new_code: str, backup: bool = True) -> Dict:
    """
    Update only a specific code section in a file, leaving the rest untouched.
    
    Args:
        file_path: Path to the file to update
        old_code: The exact code section to find and replace
        new_code: The new code to insert
        backup: Whether to create a backup before modifying
    
    Returns:
        Result dictionary with success status and details
    """
    result = {
        "success": False,
        "file": file_path,
        "backup_created": False,
        "changes_made": False,
        "message": ""
    }
    
    try:
        file_path_obj = Path(file_path)
        
        # Validate file path with base directory check
        if not validate_file_path(file_path, base_dir=str(Path.cwd())):
            result["message"] = f"Invalid file path: {file_path}"
            return result
        
        # Resolve and verify containment
        resolved_path = file_path_obj.resolve()
        try:
            resolved_path.relative_to(Path.cwd().resolve())
        except ValueError:
            result["message"] = f"Path outside working directory: {file_path}"
            return result
        
        # Check if file exists
        if not resolved_path.exists():
            result["message"] = f"File not found: {file_path}"
            return result
        
        # Read current content
        with open(file_path_obj, 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        # Create backup if requested
        if backup:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = file_path_obj.parent / f".backup_{file_path_obj.name}_{timestamp}"
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(original_content)
            result["backup_created"] = True
            result["backup_path"] = str(backup_path)
        
        # Check if old_code exists in file
        if old_code not in original_content:
            result["message"] = f"Code section not found in {file_path}"
            return result
        
        # Replace only the specific section
        updated_content = original_content.replace(old_code, new_code)
        
        # Write updated content
        with open(file_path_obj, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        
        result["success"] = True
        result["changes_made"] = True
        result["message"] = f"Successfully updated {file_path}"
        
    except Exception as e:
        result["message"] = f"Update failed: {str(e)}"
    
    return result


def create_version_snapshot(project_id: str, step_number: int, files_modified: List[str], version_dir: str = ".versions") -> Dict:
    """
    Create a version snapshot for a specific step, allowing rollback.
    
    Args:
        project_id: ID of the project
        step_number: Current step number
        files_modified: List of file paths that were modified
        version_dir: Directory to store version snapshots
    
    Returns:
        Result dictionary with snapshot details
    """
    result = {
        "success": False,
        "snapshot_id": None,
        "files_saved": [],
        "message": ""
    }
    
    try:
        from datetime import datetime
        
        # Create version directory
        version_path = Path(version_dir)
        version_path.mkdir(exist_ok=True)
        
        # Create snapshot ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_id = f"{project_id}_step{step_number}_{timestamp}"
        snapshot_path = version_path / snapshot_id
        snapshot_path.mkdir(exist_ok=True)
        
        # Save metadata
        metadata = {
            "project_id": project_id,
            "step_number": step_number,
            "timestamp": timestamp,
            "files_modified": files_modified
        }
        
        with open(snapshot_path / "metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Copy each modified file
        for file_path in files_modified:
            try:
                source = Path(file_path)
                if source.exists():
                    # Preserve directory structure in snapshot
                    rel_path = source.relative_to(Path.cwd()) if source.is_absolute() else source
                    dest = snapshot_path / rel_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy file content
                    with open(source, 'r', encoding='utf-8') as src_f:
                        content = src_f.read()
                    with open(dest, 'w', encoding='utf-8') as dest_f:
                        dest_f.write(content)
                    
                    result["files_saved"].append(str(file_path))
            except Exception as e:
                result["message"] += f"\nWarning: Could not snapshot {file_path}: {str(e)}"
        
        result["success"] = True
        result["snapshot_id"] = snapshot_id
        result["message"] = f"Snapshot created: {snapshot_id}"
        
    except Exception as e:
        result["message"] = f"Snapshot creation failed: {str(e)}"
    
    return result


def validate_project_consistency(project_path: str, expected_structure: Optional[Dict] = None) -> Dict:
    """
    Validate that project structure remains consistent and unchanged where it should be.
    
    Args:
        project_path: Path to the project root
        expected_structure: Optional dictionary of expected files/folders
    
    Returns:
        Validation result with any inconsistencies found
    """
    result = {
        "valid": True,
        "missing_files": [],
        "unexpected_changes": [],
        "message": ""
    }
    
    try:
        project_dir = Path(project_path)
        
        if not project_dir.exists():
            result["valid"] = False
            result["message"] = f"Project path not found: {project_path}"
            return result
        
        # If expected structure provided, validate against it
        if expected_structure:
            def check_structure(base_path: Path, structure_dict: Dict):
                for name, content in structure_dict.items():
                    item_path = base_path / name
                    
                    if isinstance(content, dict):
                        if not item_path.exists() or not item_path.is_dir():
                            result["missing_files"].append(str(item_path))
                            result["valid"] = False
                        else:
                            check_structure(item_path, content)
                    else:
                        if not item_path.exists() or not item_path.is_file():
                            result["missing_files"].append(str(item_path))
                            result["valid"] = False
            
            check_structure(project_dir, expected_structure)
        
        if result["valid"]:
            result["message"] = "Project structure is consistent"
        else:
            result["message"] = f"Found {len(result['missing_files'])} inconsistencies"
            
    except Exception as e:
        result["valid"] = False
        result["message"] = f"Validation failed: {str(e)}"
    
    return result


def prevent_hallucination_in_long_tasks(context: str, max_context_length: int = 8000) -> str:
    """
    Prevent hallucination by trimming and summarizing context for long tasks.
    
    Args:
        context: The full context string
        max_context_length: Maximum length to keep
    
    Returns:
        Trimmed/summarized context
    """
    if len(context) <= max_context_length:
        return context
    
    # Keep the most recent context (more relevant)
    # Also keep a summary of the beginning
    lines = context.split('\n')
    
    # Keep first 10 lines (usually task description)
    header = '\n'.join(lines[:10])
    
    # Keep last portion that fits in remaining space
    remaining_space = max_context_length - len(header) - 100  # buffer
    
    if remaining_space > 0:
        recent_context = context[-remaining_space:]
        return f"{header}\n\n[... earlier steps truncated for brevity ...]\n\n{recent_context}"
    else:
        return header[:max_context_length]
