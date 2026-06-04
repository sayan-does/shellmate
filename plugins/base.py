from abc import ABC, abstractmethod
from typing import Any


class ShellMatePlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        pass

    @property
    def author(self) -> str:
        return "Unknown"

    @property
    def description(self) -> str:
        return ""

    @abstractmethod
    def initialize(self, context: dict) -> None:
        pass


class RulePlugin(ShellMatePlugin):
    @abstractmethod
    def get_rules(self) -> list[dict]:
        pass


class DocumentationProviderPlugin(ShellMatePlugin):
    @abstractmethod
    async def retrieve(self, tool: str, query: str = None) -> dict:
        pass


class AIProviderPlugin(ShellMatePlugin):
    @abstractmethod
    def analyze_risk(self, command: str, context: dict = None) -> dict:
        pass

    @abstractmethod
    def generate_remediation(self, command: str, risk: dict, context: dict = None) -> dict:
        pass


class TerminalAdapterPlugin(ShellMatePlugin):
    @abstractmethod
    def get_hook_script(self, shell: str) -> str:
        pass

    @abstractmethod
    def get_supported_shells(self) -> list[str]:
        pass


PLUGIN_METADATA_SCHEMA = {
    "name": str,
    "version": str,
    "author": str,
    "description": str,
    "entry_point": str,
    "type": str,
}


def validate_plugin_metadata(metadata: dict) -> bool:
    for key, expected_type in PLUGIN_METADATA_SCHEMA.items():
        if key not in metadata:
            return False
        if not isinstance(metadata[key], expected_type):
            return False
    valid_types = {"rule", "documentation", "ai_provider", "terminal_adapter"}
    if metadata.get("type") not in valid_types:
        return False
    return True
