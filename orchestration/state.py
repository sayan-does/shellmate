from typing import Any, Dict, List, Optional, TypedDict


class AnalysisState(TypedDict):
    command: str
    sanitized: Optional[Dict[str, Any]]
    parsed: Optional[Dict[str, Any]]
    rule_match: Optional[Dict[str, Any]]
    cached: Optional[Dict[str, Any]]
    needs_context: bool
    watcher_context: Optional[Dict[str, Any]]
    librarian_context: Optional[Dict[str, Any]]
    merged_context: Optional[Dict[str, Any]]
    risk_analysis: Optional[Dict[str, Any]]
    remediation: Optional[Dict[str, Any]]
    output: Optional[Dict[str, Any]]
    errors: List[str]
    stages: Dict[str, float]
    agent_latency: Dict[str, float]
    early_exit: Optional[str]
    supervisor_decision: Optional[Dict[str, Any]]
    supervisor_fallback: bool
    supervisor_warning: Optional[str]
    command_guide: Optional[Dict[str, Any]]
