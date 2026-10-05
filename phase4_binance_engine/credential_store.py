"""Store API credentials in the operating system's secure credential store.

On Windows, credentials are explicitly routed to Windows Credential Manager.
On macOS and Linux, the configured system keyring must be available. Plaintext,
null, fail, and alternate file backends are rejected rather than used silently.
"""

from __future__ import annotations

import os
from typing import Final

import keyring


SERVICE_NAME: Final = "OmniTrader"
SUPPORTED_CREDENTIALS: Final = frozenset(
    {"BINANCE_API_KEY", "BINANCE_SECRET_KEY", "GEMINI_API_KEY"}
)


def _validate_name(name: str) -> str:
    normalized = name.strip().upper()
    if normalized not in SUPPORTED_CREDENTIALS:
        raise ValueError("Unsupported credential name.")
    return normalized


def _secure_backend():
    """Return an approved OS keyring backend, or fail closed."""
    if os.name == "nt":
        # Explicit selection avoids accidentally using an insecure configured
        # fallback and makes the PyInstaller build include the Windows backend.
        from keyring.backends.Windows import WinVaultKeyring

        backend = keyring.get_keyring()
        if not isinstance(backend, WinVaultKeyring):
            backend = WinVaultKeyring()
            keyring.set_keyring(backend)
        return backend

    backend = keyring.get_keyring()
    module = backend.__class__.__module__.lower()
    unsafe_modules = (
        "keyring.backends.fail",
        "keyring.backends.null",
        "keyring.backends.chainer",
        "keyring.backends.file",
        "keyrings.alt",
    )
    try:
        priority = float(backend.priority)
    except (AttributeError, TypeError, ValueError):
        priority = 0.0
    if priority <= 0 or module.startswith(unsafe_modules):
        raise RuntimeError(
            "No secure system keyring is available. Unlock or configure the OS credential store."
        )
    return backend


def check_secure_store() -> None:
    """Raise a clear error if this system has no approved credential store."""
    _secure_backend()


def get_secret(name: str) -> str | None:
    """Read one known API credential without exposing it to the UI."""
    normalized = _validate_name(name)
    _secure_backend()
    value = keyring.get_password(SERVICE_NAME, normalized)
    return value if value else None


def save_secret(name: str, value: str) -> None:
    """Save a credential to the approved OS keyring."""
    normalized = _validate_name(name)
    secret = value.strip()
    if not secret:
        raise ValueError("Credential cannot be empty.")
    _secure_backend()
    keyring.set_password(SERVICE_NAME, normalized, secret)


def delete_secret(name: str) -> None:
    """Delete a saved credential; deleting a missing value is a no-op."""
    normalized = _validate_name(name)
    _secure_backend()
    if keyring.get_password(SERVICE_NAME, normalized) is not None:
        keyring.delete_password(SERVICE_NAME, normalized)


def has_secret(name: str) -> bool:
    """Return whether a credential exists, without returning its value."""
    return get_secret(name) is not None
