from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from backend.loader import SOPLoadError, get_sops
from backend.models import ChatRequest, ChatResponse

# Refuse to start on a malformed SOP file, naming the file.
try:
    get_sops()
except SOPLoadError as e:
    raise SystemExit(f"Refusing to start: {e}")

from backend.graph import run_turn  # noqa: E402  (imported after the SOP check)

INDEX = Path(__file__).resolve().parent.parent / "frontend" / "index.html"

app = FastAPI(title="Weather Advisory Bot")


@app.get("/")
def index():
    return FileResponse(INDEX)


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
