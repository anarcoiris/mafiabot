# utils/rate_limiter.py
import time
import threading
from functools import wraps
from collections import defaultdict, deque
from typing import Callable

_lock = threading.Lock()
_buckets = defaultdict(lambda: deque())

def rate_limit(calls:int=3, per_seconds:int=10):
    """Decorator: allow `calls` per `per_seconds` per key (user or chat).
    Usage: @rate_limit(calls=3, per_seconds=10)
    The wrapped function must accept `update` as first arg with effective_user/effective_chat.
    """
    def deco(func: Callable):
        @wraps(func)
        async def wrapper(update, context, *args, **kwargs):
            try:
                user = getattr(update, "effective_user", None)
                chat = getattr(update, "effective_chat", None)
                # key per user if private, else per chat-user
                if user and chat:
                    key = f"{chat.id}:{user.id}"
                elif user:
                    key = f"user:{user.id}"
                elif chat:
                    key = f"chat:{chat.id}"
                else:
                    key = "global"
                now = time.time()
                with _lock:
                    dq = _buckets[key]
                    # pop old
                    while dq and dq[0] <= now - per_seconds:
                        dq.popleft()
                    if len(dq) >= calls:
                        # too many calls
                        # optional: raise specific exception or return a message
                        from telegram import __version__  # for typing, don't rely on it
                        raise RateLimitExceeded(key, calls, per_seconds)
                    dq.append(now)
                return await func(update, context, *args, **kwargs)
            except RateLimitExceeded:
                # bubble up to handler wrapper which will notify user
                raise
        return wrapper
    return deco

class RateLimitExceeded(Exception):
    def __init__(self, key, calls, per_seconds):
        super().__init__(f"Rate limit exceeded for {key}: {calls}/{per_seconds}s")
        self.key = key
        self.calls = calls
        self.per_seconds = per_seconds
