"""Small in-process per-client request cooldowns for the personal web app."""

from collections import deque
import threading
import time

# (maximum requests, rolling window seconds). Expensive routes get stricter limits.
ROUTE_LIMITS = {
    "/api/matches": (20, 60),
    "/api/odds": (12, 60),
    "/api/analyze": (8, 60),
    "/api/analyze-cached": (2, 15),
    "/api/daily-picks": (1, 30),
    "/api/prediction-stats": (30, 60),
}

_lock = threading.Lock()
_requests = {}
_MAX_TRACKED_KEYS = 2048


def check_request_limit(client_key, route, *, now=None):
    """Return retry seconds when a client exceeds a route limit, otherwise None."""
    limit = ROUTE_LIMITS.get(route)
    if not limit:
        return None
    maximum, window = limit
    timestamp = time.monotonic() if now is None else now
    key = (str(client_key or "unknown"), route)

    with _lock:
        history = _requests.setdefault(key, deque())
        cutoff = timestamp - window
        while history and history[0] <= cutoff:
            history.popleft()
        if len(history) >= maximum:
            return max(1, int(history[0] + window - timestamp + 0.999))
        history.append(timestamp)

        if len(_requests) > _MAX_TRACKED_KEYS:
            expired_keys = [
                tracked_key for tracked_key, requests in _requests.items()
                if not requests or requests[-1] <= timestamp - window
            ]
            for tracked_key in expired_keys:
                _requests.pop(tracked_key, None)
    return None


def reset_request_limits():
    """Clear in-memory limits; intended for isolated tests and controlled shutdowns."""
    with _lock:
        _requests.clear()
