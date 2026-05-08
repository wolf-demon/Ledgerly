"""LLM categorization helpers - Emergent + Ollama."""
import uuid

from emergentintegrations.llm.chat import LlmChat, UserMessage


async def suggest_via_emergent(sys_msg: str, user_text: str, key: str) -> str:
    chat = LlmChat(
        api_key=key,
        session_id=f"cat-{uuid.uuid4()}",
        system_message=sys_msg,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")
    resp = await chat.send_message(UserMessage(text=user_text))
    return resp.strip() if isinstance(resp, str) else str(resp)


def suggest_via_ollama(sys_msg: str, user_text: str, url: str, model: str) -> str:
    import requests
    r = requests.post(
        f"{url.rstrip('/')}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_text},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        },
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    content = (data.get("message") or {}).get("content", "")
    return content.strip() if isinstance(content, str) else str(content)
