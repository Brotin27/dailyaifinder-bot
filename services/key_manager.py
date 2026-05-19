"""
Round-Robin API Key Manager
- Add/remove/validate Gemini API keys via Telegram commands
- Auto-skip exhausted keys, auto-rotate to next available key
- Persistent storage in data/api_keys.json
"""
import json
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

from google import genai

import config

logger = logging.getLogger(__name__)


@dataclass
class APIKey:
    key: str
    label: str = ""
    status: str = "active"          # active | exhausted | invalid
    added_at: float = field(default_factory=time.time)
    last_used_at: float = 0.0
    total_uses: int = 0
    last_error: str = ""


class KeyManager:
    """Manages a pool of Gemini API keys with round-robin rotation."""

    def __init__(self, keys_file: Optional[Path] = None):
        self.keys_file = keys_file or config.API_KEYS_FILE
        self._keys: list[APIKey] = []
        self._current_index: int = 0
        self._load()

    # ── Persistence ────────────────────────────────────────────────────

    def _load(self):
        """Load keys from JSON file."""
        if self.keys_file.exists():
            try:
                raw = json.loads(self.keys_file.read_text(encoding="utf-8"))
                self._keys = [APIKey(**k) for k in raw]
            except (json.JSONDecodeError, TypeError):
                self._keys = []
        else:
            self._keys = []

    def _save(self):
        """Persist keys to JSON file."""
        self.keys_file.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(k) for k in self._keys]
        self.keys_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ── CRUD ───────────────────────────────────────────────────────────

    def add_key(self, api_key: str, label: str = "") -> str:
        """Add a new API key to the pool. Returns a status message."""
        # Check for duplicates
        for k in self._keys:
            if k.key == api_key:
                return "⚠️ This key already exists in the pool."
        
        new_key = APIKey(key=api_key, label=label or f"Key-{len(self._keys)+1}")
        self._keys.append(new_key)
        self._save()
        return f"✅ Key `{new_key.label}` added successfully! Total keys: {len(self._keys)}"

    def remove_key(self, index: int) -> str:
        """Remove a key by its 1-based index."""
        if index < 1 or index > len(self._keys):
            return f"❌ Invalid key index. You have {len(self._keys)} keys."
        removed = self._keys.pop(index - 1)
        if self._current_index >= len(self._keys):
            self._current_index = 0
        self._save()
        return f"🗑️ Key `{removed.label}` removed."

    def list_keys(self) -> str:
        """Return a formatted list of all keys with their status."""
        if not self._keys:
            return "📭 No API keys in the pool. Use /addkey to add one."
        
        lines = ["🔑 **API Key Pool:**\n"]
        for i, k in enumerate(self._keys, 1):
            status_emoji = {"active": "✅", "exhausted": "⚠️", "invalid": "❌"}.get(k.status, "❓")
            pointer = " 👈" if i - 1 == self._current_index else ""
            lines.append(
                f"`{i}.` {status_emoji} **{k.label}** — "
                f"Uses: {k.total_uses} | Status: {k.status}{pointer}"
            )
        return "\n".join(lines)

    # ── Round-Robin Selection ──────────────────────────────────────────

    def get_next_key(self) -> Optional[str]:
        """Get the next available API key using round-robin.
        Skips exhausted/invalid keys. Returns None if no keys available.
        """
        if not self._keys:
            return None

        total = len(self._keys)
        for _ in range(total):
            key_obj = self._keys[self._current_index]
            self._current_index = (self._current_index + 1) % total

            if key_obj.status == "active":
                key_obj.last_used_at = time.time()
                key_obj.total_uses += 1
                self._save()
                return key_obj.key

        return None  # All keys exhausted or invalid

    def mark_exhausted(self, api_key: str, error: str = ""):
        """Mark a key as exhausted (quota exceeded)."""
        for k in self._keys:
            if k.key == api_key:
                k.status = "exhausted"
                k.last_error = error
                self._save()
                break

    def mark_invalid(self, api_key: str, error: str = ""):
        """Mark a key as invalid (wrong key / revoked)."""
        for k in self._keys:
            if k.key == api_key:
                k.status = "invalid"
                k.last_error = error
                self._save()
                break

    def reset_all(self):
        """Reset all exhausted keys back to active (useful for daily quota reset)."""
        for k in self._keys:
            if k.status == "exhausted":
                k.status = "active"
                k.last_error = ""
        self._save()

    # ── Validation ─────────────────────────────────────────────────────

    async def validate_all_keys(self) -> str:
        """Test every key and return a summary report."""
        if not self._keys:
            return "📭 No keys to validate."

        results = []
        for i, k in enumerate(self._keys, 1):
            try:
                client = genai.Client(api_key=k.key)
                response = client.models.generate_content(
                    model=config.GEMINI_DEFAULT_MODEL,
                    contents="Say 'OK' in one word.",
                )
                if response and response.text:
                    k.status = "active"
                    k.last_error = ""
                    results.append(f"✅ `{i}. {k.label}` — Working!")
                else:
                    k.status = "invalid"
                    k.last_error = "Empty response"
                    results.append(f"❌ `{i}. {k.label}` — Empty response")
            except Exception as e:
                error_str = str(e)
                if "quota" in error_str.lower() or "429" in error_str:
                    k.status = "exhausted"
                    k.last_error = error_str[:200]
                    results.append(f"⚠️ `{i}. {k.label}` — Quota exhausted")
                else:
                    k.status = "invalid"
                    k.last_error = error_str[:200]
                    results.append(f"❌ `{i}. {k.label}` — {error_str[:100]}")

        self._save()
        return "🔍 **Key Validation Results:**\n\n" + "\n".join(results)

    def get_genai_client(self) -> Optional[genai.Client]:
        """Get a google.genai Client configured with the next available key."""
        key = self.get_next_key()
        if not key:
            return None
        return genai.Client(api_key=key)


# Singleton instance
key_manager = KeyManager()
