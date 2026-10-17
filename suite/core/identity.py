"""Identity — public IDs for organizations and accounts, and meeting join codes.

An ID is 12 digits followed by 6 uppercase letters (18 chars), e.g.
    739104825613KRMTXB
A meeting join code takes the first 4 digits and first 2 letters of the host's ID
plus 5 random digits, e.g.
    7391KR48210
People type that code to join the meeting. `secrets` gives cryptographically
random values — no cloud, purely local.
"""
from __future__ import annotations

import secrets
import string

_DIGITS = string.digits
_LETTERS = string.ascii_uppercase


def generate_id() -> str:
    """A new 18-char id: 12 digits + 6 letters."""
    digits = "".join(secrets.choice(_DIGITS) for _ in range(12))
    letters = "".join(secrets.choice(_LETTERS) for _ in range(6))
    return digits + letters


def make_meeting_code(source_id: str) -> str:
    """4 digits + 2 letters from source_id, then 5 random digits."""
    digits = [c for c in source_id if c.isdigit()]
    letters = [c for c in source_id if c.isalpha()]
    prefix = "".join(digits[:4]) + "".join(letters[:2]).upper()
    rand = "".join(secrets.choice(_DIGITS) for _ in range(5))
    return prefix + rand


def normalize_code(code: str) -> str:
    """Canonicalize user-typed codes (strip spaces/dashes, upper-case letters)."""
    return "".join(c for c in code if c.isalnum()).upper()
