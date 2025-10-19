"""
Simple local key store with lightweight encryption for user-supplied API keys.
- Stores the user's OpenRouter API key encrypted in key_store.db (JSON)
- Persists a use_user_key flag so remote requests use the user's key

Note: This uses a basic XOR + base64 obfuscation with a machine-bound derived key.
It is NOT crypto-grade security, but avoids storing plaintext. For stronger
security, integrate OS keychain or a proper cryptography library.
"""

import os
import json
import base64
import getpass
import platform
import secrets
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

BASE_DIR = Path(__file__).resolve().parent
STORE_PATH = BASE_DIR / "key_store.db"
SALT_PATH = BASE_DIR / ".keystore_salt"


class KeyStore:
    def __init__(self, store_path: Optional[Path] = None):
        self.store_path = Path(store_path) if store_path else STORE_PATH
        self.salt_path = SALT_PATH
        self._ensure_salt()

    def _ensure_salt(self) -> None:
        if not self.salt_path.exists():
            try:
                self.salt_path.write_bytes(secrets.token_bytes(32))
            except Exception:
                # Fallback: create parent dir then write
                try:
                    self.salt_path.parent.mkdir(parents=True, exist_ok=True)
                    self.salt_path.write_bytes(secrets.token_bytes(32))
                except Exception:
                    pass

    def _derive_key(self) -> bytes:
        try:
            salt = self.salt_path.read_bytes()
        except Exception:
            salt = b"oroto-default-salt"
        machine = platform.node()
        user = getpass.getuser()
        basis = f"{machine}:{user}".encode("utf-8")
        return hashlib.sha256(basis + salt).digest()

    def _xor(self, data: bytes, key: bytes) -> bytes:
        out = bytearray(len(data))
        klen = len(key)
        for i, b in enumerate(data):
            out[i] = b ^ key[i % klen]
        return bytes(out)

    def encrypt(self, plain_text: str) -> str:
        key = self._derive_key()
        raw = plain_text.encode("utf-8")
        x = self._xor(raw, key)
        return base64.b64encode(x).decode("ascii")

    def decrypt(self, token: str) -> str:
        key = self._derive_key()
        raw = base64.b64decode(token.encode("ascii"))
        x = self._xor(raw, key)
        return x.decode("utf-8")

    def _read_store(self) -> Dict:
        if self.store_path.exists():
            try:
                with open(self.store_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _write_store(self, data: Dict) -> None:
        try:
            with open(self.store_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            # Attempt directory creation then retry
            try:
                self.store_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.store_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass

    def set_user_key(self, api_key: str, provider: str = "openrouter") -> None:
        if not api_key:
            raise ValueError("API key boş olamaz")
        data = self._read_store()
        data["provider"] = provider
        data["encrypted_api_key"] = self.encrypt(api_key)
        data["use_user_key"] = True
        data["updated_at"] = datetime.utcnow().isoformat()
        self._write_store(data)

    def has_user_key(self) -> bool:
        data = self._read_store()
        return bool(data.get("encrypted_api_key"))

    def get_user_key(self) -> Optional[str]:
        data = self._read_store()
        token = data.get("encrypted_api_key")
        if not token:
            return None
        try:
            return self.decrypt(token)
        except Exception:
            return None

    def use_user_key(self) -> bool:
        data = self._read_store()
        return bool(data.get("use_user_key", False))

    def set_use_user_key(self, value: bool) -> None:
        data = self._read_store()
        data["use_user_key"] = bool(value)
        data["updated_at"] = datetime.utcnow().isoformat()
        self._write_store(data)