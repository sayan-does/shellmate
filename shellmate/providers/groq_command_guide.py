import asyncio
import json
import os
import logging
from typing import Optional

from groq import AsyncGroq

logger = logging.getLogger("shellmate.providers.groq_command_guide")

COMMAND_GUIDE_PROMPT = '''You help a terminal user understand a shell command they typed.
Respond ONLY with valid JSON:
{{"intent_guess": "Maybe you're trying to ...", "when_to_use": "...", "parameters": ["arg: what it means"], "suggested_command": "full corrected command", "example_command": "git cherry-pick abc123"}}

intent_guess: Start with "Maybe you're trying to" — infer what the user meant from their command, naming each token they typed and what it likely represents.
when_to_use: 1-2 sentences on when to use this command.
parameters: explain flags/positional args the user typed OR common ones for this tool; format "name: meaning".
suggested_command: best guess of what they meant — fill paths/names from context (cwd, git branch, project files).
example_command: a concrete runnable example using context when available.

Command: {command}
{risk_context}{context}'''


class CommandGuideError(Exception):
    pass


def _parse_guide_json(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
    data = json.loads(content)
    return {
        "intent_guess": str(data.get("intent_guess", "")),
        "when_to_use": str(data.get("when_to_use", "")),
        "parameters": list(data.get("parameters", [])),
        "suggested_command": str(data.get("suggested_command", "")),
        "example_command": str(data.get("example_command", "")),
    }


def alternatives_from_guide(guide: dict) -> list:
    """Build user-facing suggestions from a command guide dict."""
    if not guide:
        return []
    items = []
    if guide.get("intent_guess"):
        items.append(guide["intent_guess"])
    for param in (guide.get("parameters") or [])[:4]:
        items.append(param)
    cmd = guide.get("suggested_command") or guide.get("example_command")
    if cmd:
        items.append(f"Try: {cmd}")
    return items


async def generate_command_guide(
    command: str,
    *,
    context: Optional[str] = None,
    risk_reason: Optional[str] = None,
    model: Optional[str] = None,
    timeout_ms: Optional[float] = None,
) -> dict:
    from shellmate.config.credentials import load_env

    env = load_env()
    api_key = os.environ.get("GROQ_API_KEY") or env.get("GROQ_API_KEY")
    if not api_key:
        raise CommandGuideError("GROQ_API_KEY not set")

    if timeout_ms is None:
        timeout_ms = float(os.environ.get("GROQ_COMMAND_GUIDE_TIMEOUT_MS", "2000"))

    model = model or os.environ.get("GROQ_COMMAND_GUIDE_MODEL", "llama-3.1-8b-instant")
    client = AsyncGroq(api_key=api_key)
    ctx = f"\n\nContext:\n{context}" if context else ""
    risk_ctx = f"\nAnalysis note: {risk_reason}" if risk_reason else ""
    prompt = COMMAND_GUIDE_PROMPT.format(command=command, risk_context=risk_ctx, context=ctx)

    try:
        async def _call():
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=384,
            )
            return response.choices[0].message.content

        content = await asyncio.wait_for(_call(), timeout=timeout_ms / 1000.0)
        return _parse_guide_json(content)
    except asyncio.TimeoutError:
        raise CommandGuideError(f"Command guide timed out after {timeout_ms}ms")
    except json.JSONDecodeError as e:
        raise CommandGuideError(f"Invalid JSON: {e}")
    except Exception as e:
        raise CommandGuideError(str(e))
    finally:
        close = getattr(client, "aclose", None) or getattr(client, "close", None)
        if close:
            result = close()
            if asyncio.iscoroutine(result):
                await result
