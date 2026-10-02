"""Authenticated encryption for workspace secrets.

The process holds one master key (`OPSPILOT_VAULT_MASTER_KEY`). Workspace
credentials are AES-GCM sealed payloads. Decrypt only in adapter code.
"""

from __future__ import annotations

import json
import os
from hashlib import sha256

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings
from app.core.errors import OpsPilotError

_DEV_KEY_WARNING = False


class VaultError(OpsPilotError):
    code = "vault_error"


class SecretVaultService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._key = self._resolve_key(settings)

    def encrypt(self, payload: dict) -> str:
        key = self._require_key()
        nonce = os.urandom(12)
        token = AESGCM(key).encrypt(nonce, json.dumps(payload).encode("utf-8"), None)
        return (nonce + token).hex()

    def decrypt(self, ciphertext: str) -> dict:
        key = self._require_key()
        try:
            raw = bytes.fromhex(ciphertext)
            nonce, token = raw[:12], raw[12:]
            plain = AESGCM(key).decrypt(nonce, token, None)
            data = json.loads(plain.decode("utf-8"))
        except Exception as exc:
            raise VaultError("Secret payload is invalid.") from exc
        if not isinstance(data, dict):
            raise VaultError("Secret payload is invalid.")
        return data

    def rotate(self, ciphertext: str) -> str:
        return self.encrypt(self.decrypt(ciphertext))

    def redact(self, payload: dict | None) -> dict:
        if not payload:
            return {}
        return {key: "[redacted]" for key in payload}

    def _require_key(self) -> bytes:
        if self._key is None:
            raise VaultError("Vault master key is not configured.")
        return self._key

    def _resolve_key(self, settings: Settings) -> bytes | None:
        global _DEV_KEY_WARNING
        raw = settings.vault_master_key.strip()
        if len(raw) >= 32:
            return sha256(raw.encode("utf-8")).digest()
        if settings.env == "production":
            return None
        if not _DEV_KEY_WARNING:
            _DEV_KEY_WARNING = True
        material = f"{settings.jwt_secret}:opspilot-dev-vault"
        return sha256(material.encode("utf-8")).digest()
