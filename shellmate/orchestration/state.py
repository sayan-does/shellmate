from typing import Any, Dict, List, Optional, TypedDict


class AnalysisState(TypedDict, total=False):
    # Existing v2 fields
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
    
    # NEW v3 fields
    environment_context: Optional[Dict[str, Any]]  # From EnvironmentAgent
    command_chain: List[Dict[str, Any]]           # Recent commands
    chain_patterns: Dict[str, Any]                # Detected workflow patterns
    user_queries: List[str]                       # Parsed [?...] queries
    query_responses: Dict[str, str]               # Query answers
    overrides: Dict[str, Any]                     # [@...] user overrides
    risk_factors: Dict[str, float]                # Risk breakdown %
    consequence_preview: Optional[Dict[str, Any]]  # Structured what-will-happen preview from consequence_builder
