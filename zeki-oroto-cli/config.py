"""
Oroto AI Configuration Module
Reads configuration from environment variables or .env file
"""

import os
from pathlib import Path
from typing import Dict


def load_env_file(env_path: str = ".env") -> None:
    """
    Load environment variables from one or more .env files if they exist.
    
    Search order:
    1) Provided env_path (current working directory by default)
    2) The directory of this config.py module
    3) $OROTO_HOME/.env if OROTO_HOME is set
    
    Only sets variables that are not already present in the environment.
    """
    candidates = []
    try:
        candidates.append(Path(env_path))
    except Exception:
        pass
    try:
        module_dir = Path(__file__).resolve().parent
        candidates.append(module_dir / ".env")
    except Exception:
        pass
    try:
        oroto_home = os.environ.get("OROTO_HOME")
        if oroto_home:
            candidates.append(Path(oroto_home) / ".env")
    except Exception:
        pass
    
    for env_file in candidates:
        if not env_file or not env_file.exists():
            continue
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    # Parse KEY=VALUE format
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        # Only set if not already in environment
                        if key and value and not os.environ.get(key):
                            os.environ[key] = value
        except Exception:
            # Silently continue to next candidate
            pass


def get_config() -> Dict:
    """
    Get configuration from environment variables or .env file.
    
    Priority:
    1. Environment variables (Replit Secrets)
    2. .env file
    3. Default values
    
    Returns:
        Dictionary with configuration settings
    """
    # Try to load .env file first
    load_env_file()
    
    config = {
        "api_key": os.environ.get("AI_API_KEY"),
        "model": os.environ.get("MODEL", "x-ai/grok-4-fast:free"),
        "api_endpoint": os.environ.get("API_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions"),
        "max_context_length": int(os.environ.get("MAX_CONTEXT_LENGTH", "8000")),
        "temperature": float(os.environ.get("TEMPERATURE", "0.7"))
    }
    
    return config


def validate_config(config: Dict) -> bool:
    """
    Validate that required configuration is present.
    
    Args:
        config: Configuration dictionary
    
    Returns:
        True if valid, False otherwise
    """
    if not config.get("api_key"):
        return False
    
    if not config.get("model"):
        return False
    
    if not config.get("api_endpoint"):
        return False
    
    return True


# Example usage
if __name__ == "__main__":
    config = get_config()
    
    if validate_config(config):
        print("✓ Configuration is valid")
        print(f"  Model: {config['model']}")
        print(f"  Endpoint: {config['api_endpoint']}")
        print(f"  API Key: {'*' * 10} (hidden)")
    else:
        print("✗ Configuration is invalid")
        print("  Please set AI_API_KEY in Replit Secrets")
