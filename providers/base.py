from abc import ABC, abstractmethod
from typing import Optional


class AIProvider(ABC):
    @abstractmethod
    def analyze_risk(self, command: str, context: Optional[dict] = None) -> dict:
        pass

    @abstractmethod
    def generate_remediation(self, command: str, risk: dict, context: Optional[dict] = None) -> dict:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass


class ProviderError(Exception):
    def __init__(self, message: str, provider: str, status_code: Optional[int] = None):
        self.provider = provider
        self.status_code = status_code
        super().__init__(message)
