#!/usr/bin/env python3
# Auto-generated utils module
# ----------------------------
MIN_PHASE_SECONDS = 120
MAX_PHASE_SECONDS = 7 * 24 * 3600


def clamp_phase_seconds(sec: int) -> int:
    return max(MIN_PHASE_SECONDS, min(MAX_PHASE_SECONDS, sec))


def mk_callback_key() -> str:
    return str(uuid.uuid4())


def mention(uid: int, name: str) -> str:
    return f"[{name}](tg://user?id={uid})"




__all__ = [name for name in globals() if not name.startswith("_")]
