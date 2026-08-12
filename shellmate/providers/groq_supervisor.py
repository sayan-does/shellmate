import asyncio
import json
import os
import logging
from typing import Optional

from groq import AsyncGroq
from shellmate.providers.base import ProviderError

logger = logging.getLogger("shellmate.providers.groq_supervisor")

SUPERVISOR_PROMPT = '''You route shell-command analysis to context workers.
Respond ONLY with valid JSON:
{{"run_watcher": true|false, "run_librarian": true|false}}

run_watcher: true when command needs OS/shell/git/env context (git, docker, cd, env vars).
run_librarian: true when command references project files or needs repo search.
Both can be true. Both can be false for trivial commands (echo hello).

Command: {command}'''


class SupervisorError(Exception):
    pass


def _parse_supervisor_json(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
    data = json.loads(content)
    return {
        "run_watcher": bool(data.get("run_watcher", False)),
        "run_librarian": bool(data.get("run_librarian", False)),
    }


async def route_command(
    command: str,
    *,
    model: Optional[str] = None,
    timeout_ms: float = 500,
) -> dict:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise SupervisorError("GROQ_API_KEY not set")

    model = model or os.environ.get("GROQ_SUPERVISOR_MODEL", "llama-3.1-8b-instant")
    client = AsyncGroq(api_key=api_key)
    prompt = SUPERVISOR_PROMPT.format(command=command)

    try:
        async def _call():
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=64,
            )
            return response.choices[0].message.content

        content = await asyncio.wait_for(_call(), timeout=timeout_ms / 1000.0)
        return _parse_supervisor_json(content)
    except asyncio.TimeoutError:
        raise SupervisorError(f"Supervisor timed out after {timeout_ms}ms")
    except json.JSONDecodeError as e:
        raise SupervisorError(f"Invalid JSON: {e}")
    except Exception as e:
        raise SupervisorError(str(e))
    finally:
        close = getattr(client, "aclose", None) or getattr(client, "close", None)
        if close:
            result = close()
            if asyncio.iscoroutine(result):
                await result
