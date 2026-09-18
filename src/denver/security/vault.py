"""Denver Vault - Secure Windows DPAPI Credential Storage."""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

from denver.logging.logger import get_logger

logger = get_logger("vault")

_IS_WINDOWS = platform.system() == "Windows"


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _win_dpapi_encrypt(data: bytes, description: str = "DenverSecret") -> bytes:
    """Encrypt byte buffer using Windows DPAPI (CryptProtectData)."""
    if not _IS_WINDOWS:
        # Fallback for non-Windows test environments
        return base64.b64encode(data)

    in_blob = _DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_byte)))
    out_blob = _DATA_BLOB()

    # CRYPTPROTECT_UI_FORBIDDEN = 0x1
    flags = 0x1
    success = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        description,
        None,  # Optional entropy
        None,  # Reserved
        None,  # Prompt struct
        flags,
        ctypes.byref(out_blob),
    )
    if not success:
        err_code = ctypes.GetLastError()
        raise RuntimeError(f"Windows DPAPI encryption failed with error code: {err_code}")

    encrypted_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    return encrypted_bytes


def _win_dpapi_decrypt(encrypted_data: bytes) -> bytes:
    """Decrypt byte buffer using Windows DPAPI (CryptUnprotectData)."""
    if not _IS_WINDOWS:
        return base64.b64decode(encrypted_data)

    in_blob = _DATA_BLOB(len(encrypted_data), ctypes.cast(ctypes.create_string_buffer(encrypted_data), ctypes.POINTER(ctypes.c_byte)))
    out_blob = _DATA_BLOB()

    flags = 0x1
    success = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,  # Description output
        None,  # Optional entropy
        None,  # Reserved
        None,  # Prompt struct
        flags,
        ctypes.byref(out_blob),
    )
    if not success:
        err_code = ctypes.GetLastError()
        raise RuntimeError(f"Windows DPAPI decryption failed with error code: {err_code}")

    decrypted_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    return decrypted_bytes


class DenverVault:
    """Encrypted credential vault backed by the Windows Data Protection API (DPAPI)."""

    def __init__(self, vault_path: Path | str | None = None) -> None:
        if vault_path is None:
            self.vault_path = Path.home() / ".denver" / "vault.dat"
        else:
            self.vault_path = Path(vault_path)

    def _read_store(self) -> dict[str, str]:
        """Read and parse the raw encrypted store dictionary."""
        if not self.vault_path.exists():
            return {}
        try:
            content = self.vault_path.read_text(encoding="utf-8")
            if not content.strip():
                return {}
            data = json.loads(content)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to read vault file '%s': %s", self.vault_path, exc)
            return {}

    def _write_store(self, store: dict[str, str]) -> None:
        """Atomically persist the encrypted store dictionary to disk."""
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.vault_path.with_suffix(".tmp")
        try:
            temp_path.write_text(json.dumps(store, indent=2), encoding="utf-8")
            temp_path.replace(self.vault_path)
        except OSError as exc:
            logger.error("Failed to write vault store to '%s': %s", self.vault_path, exc)
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise

    def set_secret(self, name: str, value: str) -> None:
        """Encrypt a secret with Windows DPAPI and persist in the vault."""
        if not name or not isinstance(name, str):
            raise ValueError("Secret name must be a non-empty string.")
        if value is None or not isinstance(value, str):
            raise ValueError("Secret value must be a string.")

        clean_name = name.strip()
        raw_bytes = value.encode("utf-8")
        encrypted_blob = _win_dpapi_encrypt(raw_bytes, description=f"DenverSecret:{clean_name}")
        b64_str = base64.b64encode(encrypted_blob).decode("ascii")

        store = self._read_store()
        store[clean_name] = b64_str
        self._write_store(store)
        logger.debug("Successfully stored encrypted secret '%s' in Denver Vault.", clean_name)

    def get_secret(self, name: str) -> str | None:
        """Retrieve and decrypt a secret from the vault."""
        if not name:
            return None
        clean_name = name.strip()
        store = self._read_store()
        b64_str = store.get(clean_name)
        if not b64_str:
            return None

        try:
            encrypted_blob = base64.b64decode(b64_str.encode("ascii"))
            decrypted_bytes = _win_dpapi_decrypt(encrypted_blob)
            return decrypted_bytes.decode("utf-8")
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to decrypt secret '%s' from vault: %s", clean_name, exc)
            return None

    def delete_secret(self, name: str) -> bool:
        """Remove a secret from the vault."""
        if not name:
            return False
        clean_name = name.strip()
        store = self._read_store()
        if clean_name in store:
            del store[clean_name]
            self._write_store(store)
            logger.debug("Deleted secret '%s' from Denver Vault.", clean_name)
            return True
        return False

    def has_secret(self, name: str) -> bool:
        """Check if a secret exists in the vault without decrypting it."""
        if not name:
            return False
        clean_name = name.strip()
        store = self._read_store()
        return clean_name in store

    def list_secret_names(self) -> list[str]:
        """Return a sorted list of all secret keys currently held in the vault."""
        store = self._read_store()
        return sorted(store.keys())

    def clear_all_secrets(self) -> int:
        """Purge all secrets from the vault."""
        store = self._read_store()
        count = len(store)
        if count > 0:
            self._write_store({})
            logger.info("Cleared all %d secrets from Denver Vault.", count)
        return count

    def __repr__(self) -> str:
        return f"DenverVault(path={self.vault_path}, secrets_count={len(self.list_secret_names())})"

    def __str__(self) -> str:
        return self.__repr__()


# Default global vault instance
_default_vault: DenverVault | None = None


def get_vault(vault_path: Path | str | None = None) -> DenverVault:
    """Get or initialize the global Denver Vault instance."""
    global _default_vault
    if _default_vault is None or vault_path is not None:
        _default_vault = DenverVault(vault_path=vault_path)
    return _default_vault
