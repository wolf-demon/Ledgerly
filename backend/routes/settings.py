"""Settings endpoints + AI provider connectivity tests."""
import uuid

from emergentintegrations.llm.chat import LlmChat, UserMessage
from fastapi import APIRouter, HTTPException

from app_db import EMERGENT_LLM_KEY
from models import AppSettings, SettingsUpdate
from services.settings_store import get_settings, save_settings

router = APIRouter()


@router.get("/settings", response_model=AppSettings)
async def read_settings():
    return await get_settings()


@router.put("/settings", response_model=AppSettings)
async def update_settings(payload: SettingsUpdate):
    current = await get_settings()
    new_data = current.model_dump()
    for k, v in payload.model_dump(exclude_none=True).items():
        new_data[k] = v
    if new_data["ai_provider"] not in ("emergent", "ollama", "none"):
        raise HTTPException(status_code=400, detail="ai_provider must be one of: emergent, ollama, none")
    new_settings = AppSettings(**new_data)
    await save_settings(new_settings)
    return new_settings


@router.post("/settings/test-ollama")
async def test_ollama(payload: SettingsUpdate):
    """Pings an Ollama server. Returns reachable + list of installed models."""
    import requests as _req
    url = (payload.ollama_url or "http://localhost:11434").rstrip("/")
    try:
        r = _req.get(f"{url}/api/tags", timeout=4)
    except _req.exceptions.ConnectionError:
        return {
            "reachable": False,
            "error": (
                "Could not reach Ollama. Make sure Ollama is installed and running. "
                "Download from https://ollama.com/download, then run `ollama serve` if it isn't already."
            ),
        }
    except Exception as e:
        return {"reachable": False, "error": f"Connection error: {e}"}
    if r.status_code != 200:
        return {"reachable": False, "error": f"Ollama responded HTTP {r.status_code}"}
    try:
        models = [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:
        models = []
    return {"reachable": True, "models": models}


@router.post("/settings/test-emergent")
async def test_emergent(payload: SettingsUpdate):
    """Verifies the Emergent LLM key by issuing a tiny chat request."""
    key = (payload.emergent_key or "").strip() or EMERGENT_LLM_KEY
    if not key:
        return {"reachable": False, "error": "No key set. Paste your Emergent LLM key, or leave blank to use the bundled key."}
    try:
        chat = LlmChat(
            api_key=key,
            session_id=f"test-{uuid.uuid4()}",
            system_message="Reply with the single word OK.",
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        resp = await chat.send_message(UserMessage(text="ping"))
        text = (resp if isinstance(resp, str) else str(resp)).strip()[:80]
        return {"reachable": True, "sample": text}
    except Exception as e:
        msg = str(e)
        return {"reachable": False, "error": f"Emergent key test failed: {msg[:200]}"}
