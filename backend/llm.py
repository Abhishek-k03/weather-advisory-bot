import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

DEFAULT_MODEL = "openai/gpt-oss-120b"


@lru_cache
def get_llm() -> ChatGroq:
    # temperature 0: the model extracts, picks from a list and phrases; it never improvises.
    return ChatGroq(model=os.getenv("GROQ_MODEL", DEFAULT_MODEL), temperature=0, max_retries=3, timeout=30)
