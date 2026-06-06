import os
import asyncio
import aiohttp
from typing import Optional

DYNAMIC_TOOL_REGISTRY = {
    "uv": "https://docs.astral.sh/uv/",
    "claude": "https://docs.anthropic.com/claude/",
    "opencode": "https://opencode.ai/docs",
    "aider": "https://aider.chat/docs/",
    "pnpm": "https://pnpm.io/motivation",
    "bun": "https://bun.sh/docs",
    "deno": "https://docs.deno.com/",
    "docker": "https://docs.docker.com/",
    "kubectl": "https://kubernetes.io/docs/",
    "terraform": "https://developer.hashicorp.com/terraform/docs",
    "pip": "https://pip.pypa.io/en/stable/",
    "npm": "https://docs.npmjs.com/",
    "brew": "https://docs.brew.sh/",
    "cargo": "https://doc.rust-lang.org/cargo/",
    "go": "https://go.dev/doc/",
}


class Context7Client:
    def __init__(self):
        self.api_key = os.environ.get("CONTEXT7_API_KEY", "")
        self.base_url = "https://api.context7.com/v1"

    async def retrieve_documentation(self, tool: str, query: Optional[str] = None) -> dict:
        if not self.api_key:
            return self._local_fallback(tool, query)

        url = f"{self.base_url}/documentation"
        params = {"tool": tool}
        if query:
            params["query"] = query

        timeout = aiohttp.ClientTimeout(total=5)

        try:
            import aiohttp
            async with aiohttp.ClientSession(timeout=timeout) as session:
                headers = {"Authorization": f"Bearer {self.api_key}"}
                async with session.get(url, params=params, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        data["source"] = "context7"
                        return data
                    elif resp.status == 404:
                        return self._local_fallback(tool, query)
                    elif resp.status == 429:
                        return {
                            "tool": tool,
                            "error": "rate_limited",
                            "documentation": [],
                            "examples": [],
                            "source": "fallback",
                        }
                    else:
                        return self._local_fallback(tool, query)
        except ImportError:
            return self._local_fallback(tool, query)
        except asyncio.TimeoutError:
            return {
                "tool": tool,
                "error": "timeout",
                "documentation": [],
                "examples": [],
                "source": "fallback",
            }
        except Exception:
            return self._local_fallback(tool, query)

    def _local_fallback(self, tool: str, query: Optional[str] = None) -> dict:
        docs_url = DYNAMIC_TOOL_REGISTRY.get(tool, "")
        return {
            "tool": tool,
            "documentation": [f"For {tool} documentation, visit: {docs_url}"],
            "examples": [],
            "source": "built-in",
            "url": docs_url,
        }


def should_retrieve_documentation(parsed_command: dict, risk_result: dict) -> bool:
    program = parsed_command.get("program", "") if isinstance(parsed_command, dict) else ""

    if program in DYNAMIC_TOOL_REGISTRY:
        return True

    if program == "unknown" or not program:
        return True

    confidence = risk_result.get("confidence", 0)
    if confidence < 0.75:
        return True

    return False


async def retrieve_documentation_async(parsed_command, risk_result):
    if not isinstance(parsed_command, dict):
        return None

    program = parsed_command.get("program", "")
    subcommand = parsed_command.get("subcommand", "")

    if not should_retrieve_documentation(parsed_command, risk_result):
        return None

    client = Context7Client()
    query = f"{program} {subcommand}".strip() if subcommand else program
    return await client.retrieve_documentation(program, query)


# Synchronous wrapper removed - use retrieve_documentation_async directly in async context
# This function is kept for backward compatibility with non-async callers
def retrieve_documentation(parsed_command, risk_result):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        # In async context, create a task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, retrieve_documentation_async(parsed_command, risk_result))
            return future.result()
    else:
        return asyncio.run(retrieve_documentation_async(parsed_command, risk_result))
