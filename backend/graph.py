"""LangGraph wiring: nodes, edges and branching.

intake -> locate -> fetch_weather -> match -> override/compose | no_match | failure

failure and no_match return fixed text with no LLM call, so neither can drift
into a plausible-sounding guess. No SOP ID or threshold appears in this file.
"""
from langgraph.graph import END, START, StateGraph

from backend import memory, weather
from backend.loader import get_sops
from backend.models import GraphState
from backend.nodes.composer import compose_node
from backend.nodes.intake import intake_node
from backend.nodes.matcher import match_node
from backend.weather import WeatherUnavailable, describe

FAILURE_TEXT = {
    "weather": ("Sorry, I couldn't get live weather for {place} right now: either the place couldn't be "
                "found or the weather service didn't respond. I won't guess at conditions, so I can't give "
                "safety advice for this. Please check the place name or try again in a moment. "
                "No SOP was applied."),
    "missing_location": ("Which city or town are you asking about? I need a location to check live weather "
                         "before I can apply any of our safety guidance. No SOP was applied."),
    "llm": ("Sorry, something went wrong while I was processing your question, so I can't give guidance "
            "right now. Please try again. No SOP was applied."),
}


def locate_node(state: GraphState) -> dict:
    try:
        return {"location": weather.geocode(state["intent"]["location"]), "error": None}
    except WeatherUnavailable:
        return {"error": "weather"}


def fetch_weather_node(state: GraphState) -> dict:
    loc = state["location"]
    try:
        data = weather.fetch_forecast(loc["latitude"], loc["longitude"])
        return {"weather": weather.build_snapshot(data, state["intent"]["time_window"]), "error": None}
    except WeatherUnavailable:
        return {"error": "weather"}


def override_node(state: GraphState) -> dict:
    """Situational SOP: a fixed lead paragraph with its live numbers, written by code."""
    sops = get_sops()
    values = state["weather"]["values"]
    lines = []
    for sop in (sops[i] for i in state["sop_ids"] if sops[i].situational):
        live = ", ".join(describe(f, values[f]) for f in sop.conditions)
        lines.append(f"WARNING - {sop.cite_as} [high]: {' '.join(sop.advice.split())} (Live: {live}.)")
    return {"lead": "\n".join(lines)}


def no_match_node(state: GraphState) -> dict:
    categories = sorted({s.category.replace("_", " ") for s in get_sops().values() if not s.situational})
    reply = ("I do not have guidance for that. None of our safety SOPs cover this question, and I'd rather "
             "tell you so than guess. I can help with weather-related safety for: "
             f"{', '.join(categories)}. No SOP applies to this reply.")
    return {"reply": reply, "sop_ids": [], "path": "no_match"}


def failure_node(state: GraphState) -> dict:
    place = (state.get("intent") or {}).get("location") or "that location"
    reply = FAILURE_TEXT[state.get("error") or "llm"].format(place=place)
    return {"reply": reply, "sop_ids": [], "path": "failure"}


def after_intake(state: GraphState) -> str:
    if state.get("error"):
        return "failure"
    return "locate" if state["intent"]["on_topic"] else "no_match"


def after_match(state: GraphState) -> str:
    if state.get("error"):
        return "failure"
    if state.get("situational"):
        return "override"
    return "compose" if state["sop_ids"] else "no_match"


def ok_or_fail(next_node: str):
    return lambda state: "failure" if state.get("error") else next_node


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("intake", intake_node)
    g.add_node("locate", locate_node)
    g.add_node("fetch_weather", fetch_weather_node)
    g.add_node("match", match_node)
    g.add_node("override", override_node)
    g.add_node("compose", compose_node)
    g.add_node("no_match", no_match_node)
    g.add_node("failure", failure_node)

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", after_intake, ["failure", "no_match", "locate"])
    g.add_conditional_edges("locate", ok_or_fail("fetch_weather"), ["failure", "fetch_weather"])
    g.add_conditional_edges("fetch_weather", ok_or_fail("match"), ["failure", "match"])
    g.add_conditional_edges("match", after_match, ["failure", "override", "compose", "no_match"])
    g.add_edge("override", "compose")
    for node in ("compose", "no_match", "failure"):
        g.add_edge(node, END)
    return g.compile()


graph = build_graph()


def run_turn(session_id: str, message: str) -> dict:
    session = memory.get_session(session_id)
    state = graph.invoke({"message": message,
                          "history": session["history"][-6:],
                          "facts": dict(session["facts"])})
    memory.save_turn(session_id, message, state["reply"], state.get("intent"))
    return state
