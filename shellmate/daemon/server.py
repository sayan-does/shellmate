import asyncio
import json
import logging
import logging.handlers
import os
import time
from shellmate.config.defaults import get_default_config, SHELLMATE_DIR
from shellmate.daemon.pipeline import run_pipeline
from shellmate.cache.semantic_cache import preload_embedder_async
from shellmate.daemon.pipeline import run_pipeline_async
from shellmate.daemon.session import read_session, is_session_stale, validate_session_ownership

logger = logging.getLogger("shellmate.daemon")

MAX_REQUEST_SIZE = 1024 * 1024
READ_TIMEOUT = 30.0
WRITE_TIMEOUT = 30.0

STARTUP_STAGES = [
    "binding_ipc",
    "watcher_starting",
    "watcher_ready",
    "librarian_scanning",
    "librarian_ready",
    "providers_checked",
    "ready",
]

_startup_stage = "binding_ipc"
_startup_stages_completed: list[str] = []
_start_time = time.time()
_last_health_check = None
_provider_warnings: list[dict] = []


def get_provider_warnings():
    """Non-fatal provider/config warnings surfaced at startup (e.g. an
    unreachable risk model that would silently fall back to a static rating)."""
    return list(_provider_warnings)


def set_provider_warnings(warnings: list[dict]):
    global _provider_warnings
    _provider_warnings = list(warnings or [])


def get_startup_stage():
    global _startup_stage
    return _startup_stage


def get_startup_stages_completed():
    """Ordered milestones reached so far (for UI ordered reveal)."""
    return list(_startup_stages_completed)


def set_startup_stage(stage: str):
    global _startup_stage, _startup_stages_completed
    if stage in STARTUP_STAGES:
        _startup_stage = stage
        if stage not in _startup_stages_completed:
            _startup_stages_completed.append(stage)
        logger.info(f"Startup stage: {stage}")


class ShellMateDaemon:
    def __init__(self):
        self.config = get_default_config()
        self.server = None
        self._running = False

    async def handle_client(self, reader, writer):
        request_id = None
        client_addr = writer.get_extra_info('peername')
        try:
            data = await asyncio.wait_for(reader.read(MAX_REQUEST_SIZE), timeout=READ_TIMEOUT)
            if not data:
                writer.close()
                return

            if len(data) > MAX_REQUEST_SIZE:
                response = {"status": "error", "request_id": "unknown", "error": "Request too large"}
                writer.write(json.dumps(response).encode("utf-8"))
                await writer.drain()
                writer.close()
                return

            try:
                message = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError as e:
                response = {"status": "error", "request_id": "unknown", "error": f"Invalid JSON: {e}"}
                writer.write(json.dumps(response).encode("utf-8"))
                await writer.drain()
                writer.close()
                return

            request_id = message.get("request_id", "unknown")
            command = message.get("command", "")

            logger.debug(f"Received command from {client_addr}: {command[:50]} (id={request_id})")

            is_valid, error_msg = self._validate_ipc_request(command)
            if not is_valid:
                response = {"status": "error", "request_id": request_id, "error": error_msg}
                writer.write(json.dumps(response).encode("utf-8"))
                await writer.drain()
                writer.close()
                return

            if command == "/status":
                result = self._handle_status()
            elif command == "/context-gatherer":
                result = await self._handle_context_gatherer(message)
            elif command == "/analyze-partial":
                result = await self._handle_analyze_partial(message)
            elif command == "/instant-check":
                result = self._handle_instant_check(message)
            elif command == "shutdown":
                result = {"status": "ok", "message": "Shutting down"}
                asyncio.create_task(self._shutdown())
            elif command == "health":
                result = {"status": "ok", "healthy": True}
            else:
                logger.info(f"Processing command from {client_addr}: {command[:50]}")
                try:
                    from shellmate.orchestration.analysis_graph import get_analysis_graph
                    graph = get_analysis_graph()
                    
                    # Extract v3 fields from message
                    user_queries = message.get("user_queries", [])
                    overrides = message.get("overrides", {})
                    
                    result = await graph.analyze_command(command, user_queries=user_queries, overrides=overrides)
                    logger.info(f"Graph analysis completed for: {command[:50]}")
                except ImportError:
                    result = await run_pipeline_async(command)
                    logger.info(f"Pipeline completed for: {command[:50]}")
                except Exception as e:
                    logger.error(f"Pipeline error: {e}", exc_info=True)
                    raise

            response = {"status": "ok", "request_id": request_id, **result}

        except json.JSONDecodeError as e:
            response = {"status": "error", "request_id": request_id, "error": f"Invalid JSON: {e}"}
        except Exception as e:
            logger.error(f"Error processing request from {client_addr}: {e}")
            response = {"status": "error", "request_id": request_id, "error": str(e)}

        try:
            writer.write(json.dumps(response).encode("utf-8"))
            await asyncio.wait_for(writer.drain(), timeout=WRITE_TIMEOUT)
        except Exception as e:
            logger.error(f"Error writing response: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def _handle_context_gatherer(self, message):
        command = message.get("command", "") or message.get("data", {}).get("command", "")
        request_id = message.get("request_id", "unknown")

        if not command:
            return {
                "watcher": {},
                "librarian": {"matches": []},
                "timed_out": [],
                "errors": {},
                "partial": False,
                "latency_ms": 0,
                "agent_latency_ms": {"watcher": 0, "librarian": 0},
            }

        try:
            from shellmate.orchestration.analysis_graph import get_analysis_graph
            graph = get_analysis_graph()
            result = await graph.gather_context(command)
            return result
        except ImportError:
            from shellmate.agents.context_gatherer import get_context_gatherer
            gatherer = get_context_gatherer()
            result = await gatherer.gather(command)
            result["agent_latency_ms"] = {
                "watcher": result.get("agent_latency", {}).get("watcher", 0),
                "librarian": result.get("agent_latency", {}).get("librarian", 0),
            }
            return result

    def _handle_instant_check(self, message):
        """Instant catastrophic matcher — no API, target <5ms."""
        cmd = message.get("partial") or message.get("command_text") or message.get("data", {}).get("command", "")
        if not cmd:
            return {"matched": False, "error": "No command"}
        from shellmate.rules.catastrophic_matcher import match_catastrophic
        result = match_catastrophic(cmd)
        return {"pipeline": "instant_rules", **result}

    async def _handle_analyze_partial(self, message):
        """
        Fast partial analysis for autocomplete mode using full agentic pipeline.
        
        Pipeline flow for autocomplete:
        1. FAISS semantic cache (fastest ~10ms) 
        2. Instant catastrophic rules (~1ms, no API)
        3. Full agentic pipeline with skip_context flag:
           - Sanitizer (typo detection)
           - Parser (command structure)
           - Command chain agent (history patterns)
           - Rules engine (static rules)
           - Environment agent (production/dev detection, blast radius)
           - Risk analyzer (API-based with debounce)
           - Remediation (safe alternatives)
        4. Cache result in FAISS for future lookups
        """
        partial_cmd = message.get("partial", "")
        overrides = dict(message.get("overrides", {}) or {})
        
        if not partial_cmd:
            return {"status": "error", "error": "No partial command"}

        # Parse [@env=...], [?...], [!...] from typed partial (adapters pass raw buffer)
        from shellmate.cli.parser import _extract_bracket_syntax

        cleaned_partial, _queries, _directives, bracket_overrides = _extract_bracket_syntax(
            partial_cmd
        )
        if bracket_overrides:
            overrides.update(bracket_overrides)
        if cleaned_partial:
            partial_cmd = cleaned_partial

        ascii_safe = bool(message.get("ascii_safe")) or os.name == "nt"
        
        try:
            # Step 1: Check FAISS semantic cache first (FASTEST ~10ms)
            from shellmate.cache.semantic_cache import cache_lookup
            cached_result = cache_lookup(partial_cmd)
            
            if cached_result:
                # Cache hit — ensure consequence_preview (synthesize for legacy entries)
                consequence_preview = cached_result.get("consequence_preview")
                if not consequence_preview or not consequence_preview.get("what_happens"):
                    from shellmate.parser.command_parser import parse_command
                    from shellmate.orchestration.analysis_graph import (
                        _build_what_happens,
                        _build_scope,
                        _is_reversible,
                        _map_risk_to_severity,
                    )
                    parsed = parse_command(partial_cmd) or {}
                    risk_analysis = {
                        "risk": cached_result.get("risk", "MEDIUM"),
                        "reason": cached_result.get("explanation", ""),
                    }
                    consequence_preview = {
                        "what_happens": _build_what_happens(parsed, risk_analysis, {}),
                        "scope": _build_scope({}, {}),
                        "reversible": _is_reversible(parsed, risk_analysis),
                        "affected_count": None,
                        "suggested_fix": None,
                        "severity": _map_risk_to_severity(risk_analysis["risk"]),
                    }
                cache_env = cached_result.get("environment_context") or {}
                if overrides.get("env") and not cache_env.get("type"):
                    cache_env = {**cache_env, "type": overrides["env"]}
                annotation = self._format_pipeline_annotation(
                    {
                        "consequence_preview": consequence_preview,
                        "risk": cached_result.get("risk", "MEDIUM"),
                        "message": cached_result.get("explanation", ""),
                        "risk_analysis": {
                            "reason": cached_result.get("explanation", ""),
                        },
                    },
                    cache_env,
                    cached_result.get("chain_patterns") or {},
                    ascii_safe=ascii_safe,
                )
                if not annotation:
                    annotation = self._format_cached_annotation(
                        cached_result, ascii_safe=ascii_safe
                    )
                return {
                    "annotation": annotation,
                    "severity": cached_result.get("risk", "MEDIUM"),
                    "instant": False,
                    "cached": True,
                    "pipeline": "cache",
                    "consequence_preview": consequence_preview,
                    "env_type": cache_env.get("type"),
                }
            
            # Step 2: Check instant tier (catastrophic commands) - no API dependency
            from shellmate.rules.catastrophic_matcher import match_catastrophic
            catastrophic = match_catastrophic(partial_cmd)
            
            if catastrophic["matched"]:
                from shellmate.parser.command_parser import parse_command
                from shellmate.orchestration.analysis_graph import (
                    _build_what_happens,
                    _build_scope,
                    _is_reversible,
                    _map_risk_to_severity,
                )
                parsed = parse_command(partial_cmd) or {}
                risk_analysis = {
                    "risk": "CRITICAL",
                    "reason": catastrophic.get("message", ""),
                }
                consequence_preview = {
                    "what_happens": _build_what_happens(parsed, risk_analysis, {}),
                    "scope": _build_scope({}, {}),
                    "reversible": _is_reversible(parsed, risk_analysis),
                    "affected_count": None,
                    "suggested_fix": None,
                    "severity": _map_risk_to_severity("CRITICAL"),
                }
                return {
                    "annotation": catastrophic["message"],
                    "severity": catastrophic["severity"],
                    "instant": True,
                    "cached": False,
                    "pipeline": "instant_rules",
                    "consequence_preview": consequence_preview,
                }
            
            # Step 3: Run full agentic pipeline with skip_context=True for speed
            # This leverages all agents except file-system watcher/librarian:
            # - Sanitizer: typo detection
            # - Parser: command structure analysis
            # - Command chain: recent command patterns
            # - Rules: static rule matching
            # - Environment: prod/dev detection, blast radius
            # - Risk analyzer: AI-based risk classification
            # - Remediation: safe alternatives generation
            
            from shellmate.orchestration.analysis_graph import get_analysis_graph
            graph = get_analysis_graph()
            
            risk_result = await graph.analyze_command(
                partial_cmd,
                skip_context=True,  # Skip watcher/librarian for speed
                overrides=overrides,
                user_queries=[]  # No queries in autocomplete mode
            )
            
            # Step 4: Extract relevant data from pipeline result
            env_context = risk_result.get("environment_context", {}) or {}
            chain_patterns = risk_result.get("chain_patterns", {}) or {}

            # Early-exit graph paths skip env_context_node — fetch badges directly
            if not env_context.get("type"):
                try:
                    from shellmate.agents.environment import get_environment_agent

                    env_agent = get_environment_agent()
                    env_response = await env_agent.send_request(
                        "detect_context",
                        data={"overrides": overrides},
                        timeout=0.05,
                    )
                    if env_response and env_response.status == "ok":
                        env_context = env_response.data or {}
                        risk_result["environment_context"] = env_context
                except Exception as env_err:
                    logger.debug(f"Environment badge lookup failed: {env_err}")
            
            # Step 5: Cache the result in FAISS for future lookups
            from shellmate.cache.semantic_cache import cache_store
            cache_store(partial_cmd, risk_result)
            
            # Step 6: Format annotation with environment badges and chain warnings
            annotation = self._format_pipeline_annotation(
                risk_result,
                env_context,
                chain_patterns,
                ascii_safe=ascii_safe,
            )
            
            return {
                "annotation": annotation,
                "severity": risk_result.get("risk", "MEDIUM"),
                "instant": False,
                "cached": False,
                "pipeline": "full_agentic",
                "env_type": env_context.get("type"),
                "chain_detected": bool(chain_patterns.get("detected", [])),
                "latency_ms": risk_result.get("total_ms", 0),
                "consequence_preview": risk_result.get("consequence_preview"),
            }
            
        except Exception as e:
            logger.error(f"Error in analyze_partial: {e}", exc_info=True)
            # Silent fallback - return safe
            return {
                "annotation": "",
                "severity": "SAFE",
                "instant": False,
                "cached": False,
                "pipeline": "error",
                "error": str(e),
                "consequence_preview": {
                    "what_happens": "Analysis unavailable",
                    "scope": "unknown",
                    "reversible": True,
                    "affected_count": None,
                    "suggested_fix": None,
                    "severity": "info",
                },
            }
    
    def _format_cached_annotation(self, cached_result: dict, *, ascii_safe: bool = False) -> str:
        """Format annotation from cached result."""
        from shellmate.ui.annotations import format_cached_annotation

        return format_cached_annotation(cached_result, ascii_safe=ascii_safe)

    def _format_pipeline_annotation(
        self,
        risk_result: dict,
        env_context: dict,
        chain_patterns: dict,
        *,
        ascii_safe: bool = False,
    ) -> str:
        """Format annotation from pipeline result with consequence preview."""
        from shellmate.ui.annotations import format_pipeline_annotation

        return format_pipeline_annotation(
            risk_result, env_context, chain_patterns, ascii_safe=ascii_safe
        )

    def _format_legacy_annotation(
        self,
        risk_result: dict,
        env_context: dict,
        chain_patterns: dict,
        *,
        ascii_safe: bool = False,
    ) -> str:
        """Format annotation from full pipeline result with environment/chain context."""
        from shellmate.ui.annotations import format_legacy_pipeline_annotation

        return format_legacy_pipeline_annotation(
            risk_result, env_context, chain_patterns, ascii_safe=ascii_safe
        )

    def _validate_ipc_request(self, command: str) -> tuple:
        exempt_commands = ("/status", "health")
        if command in exempt_commands:
            return True, ""
        session = read_session()
        if not session:
            return False, "No active session. Run 'sm enable' first."
        if is_session_stale(session):
            return False, "Session is stale (daemon process not running). Run 'sm enable' again."
        if not validate_session_ownership(session):
            return False, "Session owner mismatch. Run 'sm disable' and 'sm enable' again."
        return True, ""

    def _handle_status(self):
        global _last_health_check
        now = time.time()
        _last_health_check = now
        return {
            "status": "ok",
            "data": {
                "startup_stage": get_startup_stage(),
                "startup_stages_completed": get_startup_stages_completed(),
                "uptime_seconds": now - _start_time,
                "last_health_check": now,
                "daemon_pid": os.getpid(),
                "provider_warnings": get_provider_warnings(),
            }
        }

    async def start(self):
        cfg = self.config["daemon"]
        host = cfg["host"]
        port = cfg["port"]

        self.server = await asyncio.start_server(
            self.handle_client, host, port
        )

        addr = self.server.sockets[0].getsockname()
        logger.info(f"Daemon listening on {addr[0]}:{addr[1]}")
        self._running = True

    async def serve(self):
        async with self.server:
            await self.server.serve_forever()

    async def stop(self):
        self._running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        logger.info("Daemon stopped")

    async def _shutdown(self):
        await self.stop()

    @property
    def is_running(self):
        return self._running


def run_daemon():
    log_dir = os.path.join(SHELLMATE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "daemon.log")
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10485760, backupCount=5
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[file_handler, logging.StreamHandler()],
    )

    daemon = ShellMateDaemon()

    async def main():
        from shellmate.agents.base import get_agent_manager, AgentManager
        from shellmate.agents.watcher import WatcherAgent
        from shellmate.agents.librarian import LibrarianAgent
        from shellmate.agents.environment import EnvironmentAgent
        from shellmate.agents.command_chain import CommandChainAgent
        from shellmate.agents.query import QueryAgent

        agent_mgr = get_agent_manager()
        watcher = WatcherAgent()
        librarian = LibrarianAgent()
        environment = EnvironmentAgent()
        command_chain = CommandChainAgent()
        query = QueryAgent()

        agent_mgr.register(watcher)
        agent_mgr.register(librarian)
        agent_mgr.register(environment)
        agent_mgr.register(command_chain)
        agent_mgr.register(query)

        set_startup_stage("binding_ipc")
        await daemon.start()

        set_startup_stage("watcher_starting")
        set_startup_stage("librarian_scanning")

        async def _start_watcher():
            await watcher.start()
            set_startup_stage("watcher_ready")

        async def _start_librarian():
            preload_embedder_async()
            await librarian.start()
            # Cap wait so a stuck indexer cannot block daemon READY forever
            await librarian.wait_until_indexed(timeout=15.0)
            set_startup_stage("librarian_ready")

        async def _start_environment():
            await environment.start()

        async def _start_command_chain():
            await command_chain.start()

        async def _start_query():
            await query.start()

        await asyncio.gather(_start_watcher(), _start_librarian(), _start_environment(), _start_command_chain(), _start_query())

        set_startup_stage("providers_checked")
        # Verify the configured risk model is actually reachable. Best-effort and
        # time-boxed so a slow/hanging provider API can never block READY.
        try:
            from shellmate.providers.router import check_risk_model_reachable
            warning = await asyncio.wait_for(check_risk_model_reachable(), timeout=6.0)
            if warning:
                set_provider_warnings([warning])
                logger.warning("Provider check: %s", warning.get("message"))
        except Exception as e:
            logger.debug(f"Risk-model reachability check skipped: {e}")

        set_startup_stage("ready")

        try:
            await daemon.serve()
            logger.info("Daemon server stopped")
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            await agent_mgr.stop_all()
            await daemon.stop()
        except Exception as e:
            logger.error(f"Daemon error: {e}", exc_info=True)
            await agent_mgr.stop_all()
            await daemon.stop()
            raise

    asyncio.run(main())
