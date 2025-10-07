# -*- coding: utf-8 -*-
"""
Password hashing helper:
- Usa bcrypt si está disponible (recomendado).
- Fallback: PBKDF2-HMAC-SHA256 (estándar lib).
- Soporta:
  - hash_password(password) -> str
  - verify_password(password, stored_hash) -> bool
  - needs_rehash(stored_hash) -> bool
  - identify_scheme(stored_hash) -> 'bcrypt' | 'pbkdf2' | 'plain'
- Auto-pepper opcional vía env: APP_PASSWORD_PEPPER
"""

from __future__ import annotations
import os, base64, hashlib, hmac, secrets
from typing import Optional

# ===== Config por defecto =====
# bcrypt rounds recomendados (cost). 12-14 es razonable para desktop.
BCRYPT_ROUNDS_DEFAULT = 12
# PBKDF2 iteraciones recomendadas 2025 (CPU bound):
PBKDF2_ITER_DEFAULT = 390_000
# Longitud del salt PBKDF2 en bytes
PBKDF2_SALT_BYTES = 16

# Pepper opcional (NO lo guardes en DB, config externa)
PEPPER = os.getenv("APP_PASSWORD_PEPPER", "").encode("utf-8")

# Intentar cargar bcrypt
try:
    import bcrypt  # type: ignore
    _HAS_BCRYPT = True
except Exception:
    bcrypt = None  # type: ignore
    _HAS_BCRYPT = False


def _apply_pepper(password: str) -> bytes:
    pw = password.encode("utf-8")
    return pw + PEPPER if PEPPER else pw


def identify_scheme(stored: str) -> str:
    if stored.startswith("$2a$") or stored.startswith("$2b$") or stored.startswith("$2y$"):
        return "bcrypt"
    if stored.startswith("pbkdf2_sha256$"):
        return "pbkdf2"
    # Si no tiene prefijo conocido, lo tratamos como texto plano legacy
    return "plain"


# ====================== BCRYPT ======================
def _bcrypt_hash(password: str, rounds: int = BCRYPT_ROUNDS_DEFAULT) -> str:
    assert _HAS_BCRYPT, "bcrypt no disponible"
    salt = bcrypt.gensalt(rounds)
    digest = bcrypt.hashpw(_apply_pepper(password), salt)
    return digest.decode("utf-8")  # "$2b$..../...."


def _bcrypt_verify(password: str, stored: str) -> bool:
    if not _HAS_BCRYPT:
        return False
    try:
        return bcrypt.checkpw(_apply_pepper(password), stored.encode("utf-8"))
    except Exception:
        return False


def _bcrypt_needs_rehash(stored: str, desired_rounds: int = BCRYPT_ROUNDS_DEFAULT) -> bool:
    if not _HAS_BCRYPT:
        return False
    try:
        # bcrypt no expone rounds directamente, pero el costo está en los primeros bytes.
        # Formato: $2b$12$...
        parts = stored.split("$")
        cost = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else desired_rounds
        return cost < desired_rounds
    except Exception:
        return False


# ====================== PBKDF2 ======================
def _pbkdf2_hash(password: str, iterations: int = PBKDF2_ITER_DEFAULT) -> str:
    salt = secrets.token_bytes(PBKDF2_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        _apply_pepper(password),
        salt,
        iterations,
        dklen=32
    )
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(dk).decode("ascii"),
    )


def _pbkdf2_verify(password: str, stored: str) -> bool:
    try:
        # formato: pbkdf2_sha256$<iter>$<salt_b64>$<hash_b64>
        parts = stored.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2].encode("ascii"))
        expected = base64.b64decode(parts[3].encode("ascii"))
        dk = hashlib.pbkdf2_hmac("sha256", _apply_pepper(password), salt, iterations, dklen=32)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def _pbkdf2_needs_rehash(stored: str, desired_iterations: int = PBKDF2_ITER_DEFAULT) -> bool:
    try:
        parts = stored.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        return iterations < desired_iterations
    except Exception:
        return False


# ====================== API Pública ======================
def hash_password(password: str) -> str:
    """Hashea usando bcrypt si existe; si no, PBKDF2."""
    if _HAS_BCRYPT:
        return _bcrypt_hash(password, BCRYPT_ROUNDS_DEFAULT)
    # ⬇️ FIX: antes se llamaba _pbkdf2_hash(PBKDF2_ITER_DEFAULT) (mal orden de args)
    return _pbkdf2_hash(password, PBKDF2_ITER_DEFAULT)



def verify_password(password: str, stored: str) -> bool:
    scheme = identify_scheme(stored)
    if scheme == "bcrypt":
        return _bcrypt_verify(password, stored)
    if scheme == "pbkdf2":
        return _pbkdf2_verify(password, stored)
    # Texto plano legacy
    return password == stored


def needs_rehash(stored: str) -> bool:
    scheme = identify_scheme(stored)
    if scheme == "bcrypt":
        return _bcrypt_needs_rehash(stored, BCRYPT_ROUNDS_DEFAULT)
    if scheme == "pbkdf2":
        return _pbkdf2_needs_rehash(stored, PBKDF2_ITER_DEFAULT)
    # Si es texto plano: sí o sí rehash
    return True


def rehash_if_needed(password: str, stored: str) -> Optional[str]:
    """
    Si el stored es texto plano o un hash débil, devuelve un hash nuevo.
    Si no hace falta, devuelve None.
    """
    if needs_rehash(stored):
        return hash_password(password)
    return None
