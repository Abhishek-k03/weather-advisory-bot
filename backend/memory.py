"""Per-session memory: chat history plus facts established earlier in the session.

Kept in process only, so it resets on restart and is never shared between
sessions. The frontend starts a new session_id on every page load.
"""
FACT_KEYS = ("location", "activity", "audience", "time_window")
MAX_HISTORY = 20

_sessions: dict[str, dict] = {}


def get_session(session_id: str) -> dict:
    return _sessions.setdefault(session_id, {"history": [], "facts": {}})


def save_turn(session_id: str, message: str, reply: str, intent: dict | None) -> None:
    session = get_session(session_id)
    session["history"] += [{"role": "user", "content": message},
                           {"role": "assistant", "content": reply}]
    del session["history"][:-MAX_HISTORY]
    if intent and intent.get("on_topic"):
        session["facts"].update({k: intent[k] for k in FACT_KEYS if intent.get(k)})
