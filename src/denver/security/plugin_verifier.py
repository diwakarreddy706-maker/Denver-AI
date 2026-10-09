"""Cryptographic Ed25519 Plugin Verification and Integrity Engine for Denver AI Assistant."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

from denver.logging.logger import get_logger

logger = get_logger("security.plugin_verifier")


def _canonical_bytes(data: dict[str, Any]) -> bytes:
    """Produce deterministic JSON canonical byte sequence ignoring existing signature fields."""
    filtered = {k: v for k, v in data.items() if k not in {"signature", "signer_pubkey"}}
    canonical_json = json.dumps(filtered, sort_keys=True, separators=(",", ":"))
    return canonical_json.encode("utf-8")


class PluginSignatureVerifier:
    """Manages Ed25519 asymmetric signature generation, verification, and hash checking for plugins."""

    @staticmethod
    def generate_keypair() -> tuple[str, str]:
        """Generate a new Ed25519 keypair for signing official or verified plugins.

        Returns:
            (private_key_hex, public_key_hex)
        """
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        priv_bytes = private_key.private_bytes_raw()
        pub_bytes = public_key.public_bytes_raw()
        return priv_bytes.hex(), pub_bytes.hex()

    @staticmethod
    def sign_manifest(manifest_dict: dict[str, Any], private_key_hex: str) -> str:
        """Sign plugin manifest canonical data using an Ed25519 private key."""
        priv_bytes = bytes.fromhex(private_key_hex.strip())
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(priv_bytes)
        payload = _canonical_bytes(manifest_dict)
        sig = private_key.sign(payload)
        return sig.hex()

    @staticmethod
    def verify_manifest(
        manifest_dict: dict[str, Any],
        signature_hex: str,
        public_key_hex: str,
    ) -> bool:
        """Verify an Ed25519 signature over the canonical manifest dictionary."""
        try:
            pub_bytes = bytes.fromhex(public_key_hex.strip())
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
            sig_bytes = bytes.fromhex(signature_hex.strip())
            payload = _canonical_bytes(manifest_dict)
            public_key.verify(sig_bytes, payload)
            return True
        except (InvalidSignature, ValueError, Exception) as exc:
            logger.warning("Plugin signature verification failed: %s", exc)
            return False

    @classmethod
    def verify_plugin_directory(
        cls,
        plugin_dir: Path | str,
        trusted_public_keys: list[str] | None = None,
    ) -> tuple[bool, str | None]:
        """Verify a plugin's manifest.json signature against trusted authority public keys."""
        p_dir = Path(plugin_dir)
        manifest_path = p_dir / "manifest.json"
        if not manifest_path.exists():
            return False, f"Manifest file missing in '{p_dir}'."

        try:
            raw_content = manifest_path.read_text(encoding="utf-8")
            data = json.loads(raw_content)
        except Exception as exc:
            return False, f"Failed to parse manifest JSON: {exc}"

        signature = data.get("signature")
        pubkey = data.get("signer_pubkey")

        if not signature or not pubkey:
            return False, "Plugin manifest is unsigned (missing 'signature' or 'signer_pubkey')."

        if trusted_public_keys and pubkey not in trusted_public_keys:
            return False, f"Signer public key '{pubkey[:16]}...' is not in the trusted authority allowlist."

        if not cls.verify_manifest(data, signature, pubkey):
            return False, "Cryptographic Ed25519 signature is invalid or manifest was tampered with."

        return True, None
