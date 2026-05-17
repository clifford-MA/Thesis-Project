# call_state.py
# ─────────────────────────────────────────────────────────────────────────────
# Shared call state — synced to the backend server so that admitting (laptop 1)
# and display screens (laptop 2+) stay in sync across the network.
#
# set_called()  → writes to local memory + POSTs to server
# get_called()  → reads from local memory (display screen fetches separately)
# clear_called()→ clears local memory + POSTs clear to server
# fetch_called()→ GETs the current state from server (used by display screens)
# ─────────────────────────────────────────────────────────────────────────────

import threading
import requests

_lock = threading.Lock()
_last_called: str | None = None

# Imported lazily to avoid circular import at module load time
def _get_api_url():
    try:
        from config import API_BASE_URL, FAST_TIMEOUT
        return API_BASE_URL, FAST_TIMEOUT
    except Exception:
        return None, 1


def set_called(queue_type: str) -> None:
    """
    Called when the Call button is pressed for a rotating queue type.
    Writes to local memory AND pushes to the server so other laptops see it.
    """
    global _last_called
    if queue_type not in ("Special Lane", "ABTC"):
        return

    with _lock:
        _last_called = queue_type
    print(f"[CALL STATE] Last called → {queue_type}")

    # Push to server in background — never block the UI
    def _push():
        api_url, timeout = _get_api_url()
        if not api_url:
            return
        try:
            requests.post(
                f"{api_url}/call-state",
                json={"queue_type": queue_type},
                timeout=timeout
            )
        except Exception as e:
            print(f"[CALL STATE] push error: {e}")

    threading.Thread(target=_push, daemon=True).start()


def get_called() -> str | None:
    """Returns the last-called rotating queue type from local memory."""
    with _lock:
        return _last_called


def clear_called() -> None:
    """Clears the override locally and on the server."""
    global _last_called
    with _lock:
        _last_called = None
    print("[CALL STATE] Cleared")

    def _push():
        api_url, timeout = _get_api_url()
        if not api_url:
            return
        try:
            requests.post(
                f"{api_url}/call-state",
                json={"queue_type": None},
                timeout=timeout
            )
        except Exception as e:
            print(f"[CALL STATE] clear push error: {e}")

    threading.Thread(target=_push, daemon=True).start()


def fetch_called() -> str | None:
    """
    Fetches the current call state FROM THE SERVER.
    Used by display screens running on a separate laptop.
    Returns "Special Lane", "ABTC", or None.
    """
    api_url, timeout = _get_api_url()
    if not api_url:
        return None
    try:
        r = requests.get(f"{api_url}/call-state", timeout=timeout)
        if r.status_code == 200:
            d = r.json()
            if d.get("success"):
                qt = d.get("queue_type")
                # Also update local cache so get_called() stays in sync
                global _last_called
                with _lock:
                    _last_called = qt
                return qt
    except Exception as e:
        print(f"[CALL STATE] fetch error: {e}")
    return None