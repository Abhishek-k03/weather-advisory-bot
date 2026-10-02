from fastapi import FastAPI, HTTPException

from backend.loader import SOPLoadError, get_sops
from backend.models import ChatRequest, ChatResponse

# Refuse to start on a malformed SOP file, naming the file.
try:
    get_sops()
except SOPLoadError as e:
    raise SystemExit(f"Refusing to start: {e}")

from backend.graph import run_turn  # noqa: E402  (imported after the SOP check)

app = FastAPI(title="Weather Advisory Bot")


@app.get("/")
def health():
    return {"status": "ok", "sops_loaded": len(get_sops())}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        state = run_turn(req.session_id, req.message)
    except SOPLoadError as e:  # an SOP file was broken while the server was running
        raise HTTPException(status_code=500, detail=str(e))
    return ChatResponse(
        reply=state["reply"],
        path=state["path"],
        sop_ids=state.get("sop_ids", []),
        location=(state.get("location") or {}).get("name"),
        weather=state.get("weather") if state["path"] in ("sop_match", "override") else None,
    )
