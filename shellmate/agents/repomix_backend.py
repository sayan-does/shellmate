import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from shellmate.config.secrets import redact_secrets
from shellmate.daemon.session import get_session_dir_path

logger = logging.getLogger("shellmate.repomix")

MAX_SNIPPET_LENGTH = 200
MAX_MATCHES = 10


class RepomixBackend:
    def __init__(self):
        self._pack_path: Optional[Path] = None
        self._pack_content: Optional[str] = None
        self._ready = False

    async def initialize(self) -> None:
        try:
            session_dir = get_session_dir_path()
            session_dir.mkdir(parents=True, exist_ok=True)
            self._pack_path = session_dir / "repomix_pack.txt"
            await self._generate_pack()
            self._ready = True
            logger.info(f"Repomix pack generated: {self._pack_path}")
        except Exception as e:
            logger.warning(f"Failed to initialize repomix backend: {e}")
            self._ready = False

    async def _generate_pack(self) -> None:
        project_root = Path.cwd()
        lines = []
        eligible_extensions = {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".rs", ".go", ".java", ".rb",
            ".php", ".c", ".cpp", ".h", ".hpp", ".cs", ".swift", ".kt", ".scala",
            ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd",
            ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
            ".md", ".rst", ".txt", ".html", ".css", ".scss", ".less",
            ".xml", ".svg", ".dockerfile",
            ".env", ".env.example",
            ".gitignore", ".gitattributes",
            ".editorconfig", ".prettierrc", ".eslintrc",
        }
        exclude_dirs = {
            ".git", "__pycache__", "node_modules", "venv", ".venv", "env",
            ".env", "virtualenv", ".tox", ".nox",
            ".mypy_cache", ".pytest_cache", ".ruff_cache",
            "target", "build", "dist", ".next", ".nuxt",
            ".cache", ".npm", ".yarn", ".pnpm-store",
            "vendor", ".bundle", "deps", "third_party",
            ".idea", ".vscode", ".vs",
        }
        exclude_files = {
            "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
            ".DS_Store", "Thumbs.db",
        }

        for root, dirs, files in os.walk(project_root, topdown=True):
            rel_root = Path(root).relative_to(project_root)
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for f in files:
                if f in exclude_files:
                    continue
                file_path = Path(root) / f
                ext = file_path.suffix.lower()
                if ext not in eligible_extensions and f.lower() not in ("makefile", "dockerfile", "procfile"):
                    continue
                try:
                    rel_path = file_path.relative_to(project_root)
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                    content = redact_secrets(content)
                    lines.append(f"## {rel_path}")
                    lines.append("```" + (ext.lstrip(".") if ext else "text"))
                    lines.append(content)
                    lines.append("```")
                    lines.append("")
                except (OSError, UnicodeDecodeError):
                    continue

        content = "\n".join(lines)
        if self._pack_path:
            self._pack_path.write_text(content, encoding="utf-8")
        self._pack_content = content

    async def search(self, query: str) -> Dict[str, Any]:
        if not self._ready or not self._pack_content:
            return {"matches": []}

        start = time.monotonic()
        tokens = self._tokenize(query)
        if not tokens:
            return {"matches": []}

        current_file = None
        file_scores: Dict[str, float] = {}
        file_snippets: Dict[str, str] = {}
        file_sizes: Dict[str, int] = {}

        lines = self._pack_content.split("\n")
        for line in lines:
            if line.startswith("## "):
                current_file = line[3:].strip()
                continue
            if current_file:
                for token in tokens:
                    if token in line.lower():
                        file_scores[current_file] = file_scores.get(current_file, 0) + 1
                        if current_file not in file_snippets and line.strip():
                            snippet = line.strip()
                            if len(snippet) > MAX_SNIPPET_LENGTH:
                                snippet = snippet[:MAX_SNIPPET_LENGTH] + "..."
                            file_snippets[current_file] = snippet

        ranked = sorted(file_scores.items(), key=lambda x: (-x[1], x[0]))
        matches = []
        for path, score in ranked[:MAX_MATCHES]:
            snippet = file_snippets.get(path, "")
            matches.append({
                "path": path,
                "score": round(score, 1),
                "snippet": snippet,
                "size": file_sizes.get(path, 0),
            })

        elapsed = (time.monotonic() - start) * 1000
        logger.debug(f"Repomix search for '{query}': {len(matches)} matches in {elapsed:.0f}ms")
        return {"matches": matches, "latency_ms": round(elapsed, 1)}

    def _tokenize(self, text: str) -> List[str]:
        parts = re.split(r"[/\\\.\-_ ]", text.lower())
        result = []
        for part in parts:
            if len(part) >= 2:
                result.append(part)
            sub_parts = re.findall(r"[a-z]+|[A-Z][a-z]*|\d+", part)
            for sp in sub_parts:
                sp_lower = sp.lower()
                if len(sp_lower) >= 2 and sp_lower != part:
                    result.append(sp_lower)
        return list(set(result))

    async def cleanup(self) -> None:
        self._ready = False
        self._pack_content = None
        if self._pack_path and self._pack_path.exists():
            try:
                self._pack_path.unlink()
                logger.info("Repomix pack deleted")
            except OSError as e:
                logger.warning(f"Failed to delete repomix pack: {e}")
        self._pack_path = None

    @property
    def is_ready(self) -> bool:
        return self._ready


_repomix_backend: Optional[RepomixBackend] = None


def get_repomix_backend() -> RepomixBackend:
    global _repomix_backend
    if _repomix_backend is None:
        _repomix_backend = RepomixBackend()
    return _repomix_backend
