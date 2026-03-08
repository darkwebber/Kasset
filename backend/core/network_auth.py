"""
Network Authentication for Kasset.

Security model:
- On first boot, the local user sets a network access password.
- The password is hashed with scrypt (random salt) and stored in ~/.kasset/network_auth.json.
- Network (non-local) clients must authenticate with this password to get a session token.
- Session tokens are cryptographically random, stored in memory, and expire after 24 hours.
- After 3 failed login attempts from a single IP, that IP is locked out for 1 hour.
- Local clients (127.0.0.1, ::1) bypass authentication entirely.
"""

import hashlib
import json
import os
import secrets
import time
import threading
from pathlib import Path
from typing import Optional, Dict

AUTH_FILE = Path.home() / ".kasset" / "network_auth.json"
TOKEN_EXPIRY_SECONDS = 24 * 60 * 60  # 24 hours
LOCKOUT_DURATION_SECONDS = 60 * 60   # 1 hour
MAX_FAILED_ATTEMPTS = 3
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64

_lock = threading.Lock()

# In-memory stores
_sessions: Dict[str, float] = {}          # token -> expiry_timestamp
_failed_attempts: Dict[str, list] = {}    # ip -> [timestamp, timestamp, ...]


def _persist_sessions():
    """Save active sessions to the auth file (must be called under _lock)."""
    try:
        data = {}
        if AUTH_FILE.exists():
            try:
                data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        data["sessions"] = {t: exp for t, exp in _sessions.items()}
        AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
        AUTH_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            os.chmod(AUTH_FILE, 0o600)
        except OSError:
            pass
    except Exception:
        pass


def load_sessions_from_disk():
    """Restore sessions from disk on startup. Prunes expired ones."""
    now = time.time()
    with _lock:
        try:
            if AUTH_FILE.exists():
                data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
                saved = data.get("sessions", {})
                for token, expiry in saved.items():
                    if isinstance(expiry, (int, float)) and expiry > now:
                        _sessions[token] = expiry
                # Persist cleaned set
                if saved:
                    _persist_sessions()
        except (json.JSONDecodeError, OSError):
            pass


def _load_auth_data() -> dict:
    """Load auth data from disk."""
    if AUTH_FILE.exists():
        try:
            return json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_auth_data(data: dict):
    """Persist auth data to disk."""
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    # Restrict file permissions (owner read/write only)
    try:
        os.chmod(AUTH_FILE, 0o600)
    except OSError:
        pass


def _hash_password(password: str, salt: bytes) -> str:
    """Hash a password with scrypt and return hex digest."""
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return dk.hex()


def is_password_configured() -> bool:
    """Check if a network password has been set."""
    data = _load_auth_data()
    return bool(data.get("password_hash") and data.get("salt"))


def setup_password(password: str) -> bool:
    """
    Set up the network access password.
    Returns True on success. Fails if password is too short.
    Can be called again to change the password (invalidates all sessions).
    """
    if len(password) < 8:
        return False

    salt = secrets.token_bytes(32)
    pw_hash = _hash_password(password, salt)

    _save_auth_data({
        "password_hash": pw_hash,
        "salt": salt.hex(),
        "created_at": time.time(),
    })

    # Invalidate all existing sessions on password change
    with _lock:
        _sessions.clear()

    return True


def verify_password(password: str) -> bool:
    """Verify a password against the stored hash."""
    data = _load_auth_data()
    stored_hash = data.get("password_hash")
    salt_hex = data.get("salt")

    if not stored_hash or not salt_hex:
        return False

    salt = bytes.fromhex(salt_hex)
    computed = _hash_password(password, salt)

    # Constant-time comparison to prevent timing attacks
    return secrets.compare_digest(computed, stored_hash)


def is_ip_locked_out(ip: str) -> bool:
    """Check if an IP is currently locked out due to failed attempts."""
    with _lock:
        attempts = _failed_attempts.get(ip, [])
        if not attempts:
            return False

        # Clean old attempts (older than lockout window)
        now = time.time()
        recent = [t for t in attempts if now - t < LOCKOUT_DURATION_SECONDS]
        _failed_attempts[ip] = recent

        return len(recent) >= MAX_FAILED_ATTEMPTS


def record_failed_attempt(ip: str):
    """Record a failed login attempt for an IP."""
    with _lock:
        if ip not in _failed_attempts:
            _failed_attempts[ip] = []
        _failed_attempts[ip].append(time.time())


def get_lockout_remaining(ip: str) -> int:
    """Get seconds remaining in lockout for an IP. Returns 0 if not locked out."""
    with _lock:
        attempts = _failed_attempts.get(ip, [])
        if len(attempts) < MAX_FAILED_ATTEMPTS:
            return 0
        # Lockout started at the 3rd failed attempt
        oldest_relevant = sorted(attempts)[-MAX_FAILED_ATTEMPTS]
        remaining = LOCKOUT_DURATION_SECONDS - (time.time() - oldest_relevant)
        return max(0, int(remaining))


def create_session() -> str:
    """Create a new session token. Persists to disk for restart resilience."""
    token = secrets.token_urlsafe(48)
    with _lock:
        _sessions[token] = time.time() + TOKEN_EXPIRY_SECONDS
        _persist_sessions()
    return token


def validate_session(token: str) -> bool:
    """Check if a session token is valid and not expired."""
    if not token:
        return False
    with _lock:
        expiry = _sessions.get(token)
        if expiry is None:
            return False
        if time.time() > expiry:
            del _sessions[token]
            return False
        return True


def revoke_session(token: str):
    """Revoke a session token."""
    with _lock:
        _sessions.pop(token, None)
        _persist_sessions()


def cleanup_sessions():
    """Remove expired sessions. Called periodically."""
    now = time.time()
    with _lock:
        expired = [t for t, exp in _sessions.items() if now > exp]
        for t in expired:
            del _sessions[t]
        if expired:
            _persist_sessions()
