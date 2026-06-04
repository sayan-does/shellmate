# ShellMate MVP - End-to-End Implementation Plan

## Goal
Build ShellMate from greenfield to MVP-complete: Python-based command safety tool with daemon architecture, multi-shell support (Bash/PowerShell/Zsh), AI-powered risk analysis (Groq + OpenRouter), semantic caching, Context7 documentation lookup, and cross-platform compatibility.

## Implementation Strategy
Top-down approach: CLI → daemon → analysis pipeline → AI integration → comprehensive testing

---

## Phase 1: Project Foundation

- [ ] Create `pyproject.toml` with Python 3.10+, dependencies: click, asyncio, aiohttp, faiss-cpu, sentence-transformers, groq, openai (for OpenRouter) → Verify: `pip install -e .` succeeds
- [ ] Create directory structure: `cli/`, `daemon/`, `ipc/`, `adapters/`, `environment/`, `sanitizer/`, `parser/`, `rules/`, `cache/`, `agents/`, `providers/`, `documentation/`, `plugins/`, `config/`, `tests/`
- [ ] Add `cli/__init__.py` and `cli/main.py` with Click CLI skeleton: `shellmate --version` → Verify: `shellmate --version` returns version string
- [ ] Create `config/defaults.py` with default config schema (latency targets, provider endpoints, cache settings) → Verify: Import succeeds, returns dict
- [ ] Initialize git repository, add `.gitignore` (Python, venv, cache, logs, `.env`) → Verify: `git status` shows clean state

---

## Phase 2: Environment Detection Engine

- [ ] Create `environment/detector.py` with `detect_environment()` function → Returns: `{"os": str, "shell": str, "environment": str, "terminal": str}`
- [ ] Implement OS detection (Linux/Windows/macOS) using `platform` module → Verify: Correct OS returned on current system
- [ ] Implement shell detection (bash/zsh/fish/powershell/cmd) via `$SHELL`, `$0`, and Windows registry checks → Verify: Detects current shell correctly
- [ ] Implement environment detection (native/wsl/container/ssh) via `/proc/version`, `WSL_DISTRO_NAME`, container markers → Verify: Returns `native` on bare metal, `wsl` in WSL
- [ ] Implement terminal detection via `$TERM_PROGRAM`, fallback to `unknown` → Verify: Detects Windows Terminal, iTerm2, or returns `unknown`
- [ ] Add CLI command `shellmate doctor` that prints detected environment JSON → Verify: `shellmate doctor` shows correct environment

---

## Phase 3: Daemon Architecture + IPC

- [ ] Create `daemon/server.py` with asyncio TCP server (Unix socket on Linux/macOS, named pipe on Windows) → Verify: Server starts without errors
- [ ] Implement `daemon/lifecycle.py` with start/stop/status management, PID file handling → Verify: Daemon starts in background, PID file created
- [ ] Create `ipc/client.py` with async client connecting to daemon socket/pipe → Verify: Client connects to running daemon
- [ ] Implement request/response protocol: JSON messages with `{"command": str, "request_id": str}` → Verify: Client sends command, receives `{"status": "ok", "request_id": str}`
- [ ] Add daemon logging to `~/.shellmate/logs/daemon.log` with rotation → Verify: Log file created with startup message
- [ ] Implement CLI commands: `shellmate enable` (start daemon), `shellmate disable` (stop daemon), `shellmate status` (check daemon) → Verify: Each command works correctly

---

## Phase 4: Parser + Sanitizer

- [ ] Create `parser/command_parser.py` using `shlex.split()` to parse commands → Returns: `{"program": str, "subcommand": str, "flags": list, "arguments": list}`
- [ ] Handle parsing edge cases: quoted strings, escaped chars, pipes, redirects → Verify: `git commit -m "test message"` parses correctly
- [ ] Create `sanitizer/typo_detector.py` with whitespace normalization, trailing char detection → Verify: `git push origin main,` returns correction
- [ ] Implement duplicate flag detection (e.g., `--force --force`) → Verify: Detects duplicate and warns
- [ ] Implement basic shell syntax validation (unmatched quotes, invalid operators) → Verify: Detects `git commit -m "unclosed quote` as malformed
- [ ] Integrate sanitizer into daemon request flow → Verify: Malformed commands return early with corrections

---

## Phase 5: Rule Engine

- [ ] Create `rules/engine.py` with rule matching against parsed command structure → Returns: `{"matched": bool, "rule_id": str, "risk": str}`
- [ ] Create `rules/definitions/` with YAML rule files for dangerous commands (rm -rf, mkfs, chmod 777, dd, curl | bash) → Verify: Rules load without errors
- [ ] Implement pattern matching: exact program match, flag presence, argument patterns → Verify: `rm -rf /` matches deletion rule
- [ ] Add rule categories: file_deletion, filesystem, permissions, process_control, network_execution, system_destruction → Verify: Each category represented
- [ ] Create 20+ built-in rules covering MVP acceptance criteria patterns → Verify: Rule count >= 20
- [ ] Add CLI command `shellmate update-rules` (for future community packs; MVP just validates local rules) → Verify: Command validates and reloads rules

---

## Phase 6: Semantic Cache (FAISS)

- [ ] Install `faiss-cpu` and `sentence-transformers`, load model `all-MiniLM-L6-v2` → Verify: Model loads in <5 seconds
- [ ] Create `cache/semantic_cache.py` with FAISS index initialization → Verify: Index created in `~/.shellmate/cache/`
- [ ] Implement embedding generation for command strings → Verify: "rm -rf /tmp/test" generates 384-dim vector
- [ ] Implement cache lookup with similarity threshold 0.92 → Returns cached result or None
- [ ] Implement cache storage: command + risk + confidence + explanation + alternatives + timestamp → Verify: Entry stored and retrievable
- [ ] Add cache expiration (30 days default) and size limit (10k entries) → Verify: Old entries purged on lookup
- [ ] Add CLI command `shellmate cache clear` → Verify: Cache directory emptied

---

## Phase 7: AI Provider Infrastructure

- [ ] Create `providers/base.py` with abstract `AIProvider` class (methods: `analyze_risk`, `generate_remediation`) → Verify: Class defines interface
- [ ] Create `providers/groq_provider.py` implementing Risk Agent with Groq API → Returns: `{"risk": str, "confidence": float, "reason": str}`
- [ ] Create `providers/openrouter_provider.py` implementing Remediation Agent → Returns: `{"explanation": str, "alternatives": list}`
- [ ] Implement OpenRouter cascade: GPT-4o-mini → Llama-3.3-70b → Qwen2.5-72b (no Ollama) → Verify: Falls back on 429/500 errors
- [ ] Create `providers/router.py` with provider selection logic and fallback handling → Verify: Fallback works when primary fails
- [ ] Load API keys from environment variables `GROQ_API_KEY`, `OPENROUTER_API_KEY` → Verify: Raises clear error if missing
- [ ] Add provider status to `shellmate status` command → Verify: Shows configured providers and connectivity

---

## Phase 8: Documentation Intelligence Layer (Context7 MCP)

- [ ] Install MCP client library (if available) or implement HTTP client for Context7 API → Verify: Client initialization succeeds
- [ ] Create `documentation/context7_client.py` with async document retrieval → Returns: `{"tool": str, "documentation": list, "examples": list}`
- [ ] Implement dynamic tool registry: uv, claude, opencode, aider, pnpm, bun, deno, docker, kubectl, terraform → Verify: Registry contains 10+ tools
- [ ] Implement trigger logic: unrecognized command OR confidence < 0.75 OR command in registry → Verify: Correct trigger for `uv run script.py`
- [ ] Integrate documentation lookup into daemon pipeline (after rule engine, before AI) → Verify: Documentation retrieved for registered tools
- [ ] Handle Context7 API errors gracefully (timeout, rate limit, 404) → Verify: Pipeline continues on documentation failure

---

## Phase 9: Decision Pipeline Integration

- [ ] Wire up complete pipeline in `daemon/pipeline.py`: sanitizer → parser → rule engine → cache → documentation → risk agent → remediation agent
- [ ] Implement early exit logic: return on sanitizer correction, rule match, or cache hit → Verify: Pipeline stops early when appropriate
- [ ] Add confidence threshold logic: skip AI if rule engine confidence >= 0.9 → Verify: High-confidence rules bypass AI
- [ ] Implement risk level determination (SAFE/LOW/MEDIUM/HIGH/CRITICAL) → Verify: Correct risk levels assigned
- [ ] Create response formatter with user-friendly output → Verify: Response includes risk, explanation, alternatives
- [ ] Add latency tracking: log pipeline stage durations → Verify: Logs show <200ms for cache hits, <5s for AI calls

---

## Phase 10: Terminal Adapters (Bash, Zsh, PowerShell)

- [ ] Create `adapters/bash_adapter.sh` with `PROMPT_COMMAND` hook calling `shellmate analyze` → Verify: Hook intercepts commands
- [ ] Create `adapters/zsh_adapter.zsh` with `preexec` hook calling `shellmate analyze` → Verify: Hook intercepts commands in Zsh
- [ ] Create `adapters/powershell_adapter.ps1` with `PSConsoleHostReadLine` override → Verify: Hook intercepts commands in PowerShell
- [ ] Implement `cli/commands/analyze.py` that sends command to daemon and displays result → Verify: `shellmate analyze "rm -rf /"` returns HIGH risk
- [ ] Implement adapter installation in `cli/commands/install.py`: detects shell, copies hook to appropriate rc file → Verify: `shellmate install` adds hook to `.bashrc`/`.zshrc`/`$PROFILE`
- [ ] Add uninstall logic in `cli/commands/uninstall.py`: removes hooks from rc files → Verify: `shellmate uninstall` removes hooks cleanly
- [ ] Handle edge cases: existing ShellMate installation, multiple shells, permission errors → Verify: Installation idempotent, errors clear

---

## Phase 11: User Experience Levels

- [ ] Implement risk level display formatting: SAFE (green/no warning), LOW (info), MEDIUM (yellow warning), HIGH (red warning), CRITICAL (blocking confirmation) → Verify: Each level displays correctly
- [ ] Add CRITICAL risk blocking: require user to type "yes" or "y" to proceed → Verify: `rm -rf /` blocks execution until confirmation
- [ ] Implement alternative suggestion display: numbered list with brief descriptions → Verify: Alternatives shown clearly
- [ ] Add "proceed anyway" option for all risk levels → Verify: User can override any warning
- [ ] Implement quiet mode flag `--quiet` to suppress warnings (for scripts) → Verify: `shellmate analyze --quiet "command"` returns minimal output
- [ ] Store user override decisions in `~/.shellmate/overrides.json` (optional learning signal for future) → Verify: File created on override

---

## Phase 12: CLI Commands (Remaining)

- [ ] Implement `shellmate config` command to print current config → Verify: Shows provider keys (redacted), cache settings, latency targets
- [ ] Add `shellmate config set <key> <value>` to update config → Verify: Updates persisted to `~/.shellmate/config.json`
- [ ] Implement `shellmate logs` command (tail last 50 lines of daemon log) → Verify: Shows recent daemon activity
- [ ] Implement `shellmate providers` command listing provider status and latency → Verify: Shows Groq + OpenRouter status
- [ ] Add `shellmate version` flag (`--version`, `-v`) → Verify: Prints ShellMate version
- [ ] Add help text and examples to all CLI commands → Verify: `shellmate --help` shows comprehensive usage

---

## Phase 13: Observability + Logging

- [ ] Implement structured logging with JSON output for machine parsing → Verify: Log entries are valid JSON
- [ ] Add event tracking for all observability events in spec: environment.detected, rule.match, cache.hit/miss, provider.request/failure, documentation.retrieved, mcp.retrieved, daemon.lifecycle → Verify: Each event type logged
- [ ] Implement log levels: DEBUG (all events), INFO (user-visible), WARNING (degraded), ERROR (failures) → Verify: Log level filtering works
- [ ] Add performance metrics: command analysis duration, cache hit rate, provider latencies → Verify: Metrics logged to `~/.shellmate/metrics.json`
- [ ] Create `shellmate doctor --verbose` to run diagnostics and output detailed health report → Verify: Shows environment, daemon status, provider connectivity, cache stats

---

## Phase 14: Plugin System Architecture

- [ ] Define plugin interfaces in `plugins/base.py`: `RulePlugin`, `DocumentationProviderPlugin`, `AIProviderPlugin`, `TerminalAdapterPlugin` → Verify: Interfaces defined with abstract methods
- [ ] Create plugin discovery system: load plugins from `~/.shellmate/plugins/` → Verify: Plugin directory scanned on daemon start
- [ ] Implement plugin registration in daemon: plugins can extend rule engine, add providers, add adapters → Verify: Mock plugin loads successfully
- [ ] Add plugin metadata schema: name, version, author, description, entry point → Verify: Metadata validated on load
- [ ] Document plugin development guide in `docs/plugin-development.md` → Verify: Guide includes interface examples and installation instructions
- [ ] Note: Community plugins are post-MVP; MVP only needs the architecture and one example plugin

---

## Phase 15: Packaging + Distribution

- [ ] Configure `pyproject.toml` for PyPI: package metadata, entry points, classifiers → Verify: `python -m build` creates wheel
- [ ] Add `setup.py` for editable installs and legacy compatibility → Verify: `pip install -e .` works
- [ ] Create `MANIFEST.in` to include adapters, rules, config files in distribution → Verify: Wheel contains all necessary files
- [ ] Write `README.md` with installation instructions, quick start, examples → Verify: README clear and complete
- [ ] Create `LICENSE` file (MIT per spec) → Verify: License text correct
- [ ] Add `requirements.txt` with pinned versions for reproducibility → Verify: `pip install -r requirements.txt` installs exact versions
- [ ] Test installation in clean virtual environment → Verify: `pip install dist/shellmate-*.whl` succeeds, `shellmate --help` works

---

## Phase 16: Comprehensive Test Suite

- [ ] Create `tests/unit/` directory with unit tests for each component: sanitizer, parser, rule engine, cache, providers → Target: >80% coverage
- [ ] Write `tests/unit/test_sanitizer.py`: test whitespace normalization, trailing chars, duplicate flags, syntax validation → Verify: All tests pass
- [ ] Write `tests/unit/test_parser.py`: test command parsing, edge cases, quotes, escapes → Verify: All tests pass
- [ ] Write `tests/unit/test_rule_engine.py`: test pattern matching, rule loading, category filtering → Verify: All tests pass
- [ ] Write `tests/unit/test_cache.py`: test FAISS operations, similarity threshold, expiration → Verify: All tests pass
- [ ] Write `tests/unit/test_providers.py`: test provider fallback chain, API error handling (mock APIs) → Verify: All tests pass
- [ ] Create `tests/integration/` with integration tests for pipeline flows: command → daemon → response → Verify: E2E request flow works
- [ ] Write `tests/integration/test_pipeline.py`: test complete decision pipeline with mocked AI providers → Verify: Pipeline returns correct results
- [ ] Create `tests/e2e/` with shell-specific E2E tests for Bash, Zsh, PowerShell → Verify: Hooks work in each shell
- [ ] Write `tests/e2e/test_bash_adapter.sh`: test Bash hook installation and command interception → Verify: Commands intercepted correctly
- [ ] Write `tests/e2e/test_zsh_adapter.zsh`: test Zsh hook installation and command interception → Verify: Commands intercepted correctly
- [ ] Write `tests/e2e/test_powershell_adapter.ps1`: test PowerShell hook installation and command interception → Verify: Commands intercepted correctly
- [ ] Run full test suite with `pytest` → Verify: All tests pass
- [ ] Generate coverage report with `pytest-cov` → Verify: Coverage >80%
- [ ] Set up test fixtures and mocks for AI providers to avoid API costs during testing → Verify: Tests run without API keys

---

## Phase 17: Bug Fixing + MVP Validation

- [ ] Run `shellmate install` on Linux (Bash and Zsh) → Verify: Installation succeeds, hooks work
- [ ] Run `shellmate install` on Windows (PowerShell) → Verify: Installation succeeds, hooks work
- [ ] Run `shellmate install` on macOS (Zsh) → Verify: Installation succeeds, hooks work
- [ ] Run `shellmate install` in WSL (Bash) → Verify: Installation succeeds, hooks work
- [ ] Test sanitizer with typos: `git push origin main,`, `rm -rf /tmp/test  ` → Verify: Corrections provided
- [ ] Test rule engine with dangerous commands: `rm -rf /`, `chmod -R 777 /`, `dd if=/dev/zero of=/dev/sda` → Verify: HIGH/CRITICAL risk detected
- [ ] Test semantic cache: run same command twice → Verify: Second run returns cached result in <200ms
- [ ] Test Groq risk analysis with novel command → Verify: Risk classification returned in <5s
- [ ] Test OpenRouter remediation with dangerous command → Verify: Alternatives provided
- [ ] Test OpenRouter fallback cascade: disable primary model, verify fallback → Verify: Fallback to secondary model works
- [ ] Test Context7 documentation retrieval: `uv run script.py` → Verify: Documentation retrieved
- [ ] Test offline resilience: disconnect network, run cached command → Verify: Works from cache
- [ ] Test offline failure: disconnect network, run novel command → Verify: Clear error message, no crash
- [ ] Review all 16 MVP acceptance criteria from spec → Verify: All criteria met
- [ ] Fix any bugs discovered during validation → Verify: Fixes verified with tests
- [ ] Run full test suite again after fixes → Verify: All tests still pass

---

## Done When

- [ ] All 16 MVP acceptance criteria pass
- [ ] `pip install shellmate` works in clean environment
- [ ] `shellmate enable` installs hooks for Bash, Zsh, PowerShell automatically
- [ ] Dangerous commands (`rm -rf /`) are detected and blocked with CRITICAL warning
- [ ] Safe commands pass through with <200ms latency
- [ ] AI analysis completes in <5 seconds for novel commands
- [ ] Test coverage >80% with all tests passing
- [ ] Documentation complete (README, plugin guide, CLI reference)
- [ ] Package built and ready for PyPI distribution

---

## Notes

**Critical Path**: Phases 1-3 (foundation + daemon) → Phase 4-6 (analysis pipeline) → Phase 7-9 (AI integration) → Phase 10 (terminal adapters) must be sequential. Phases 11-14 can be parallelized. Phases 15-17 are final validation.

**Dependencies**: Groq and OpenRouter API keys required from Phase 7 onward. Context7 access required for Phase 8.

**Deferred to Post-MVP**: Fish, CMD, Git Bash adapters; Warp/WezTerm/Kitty terminal-specific features; community plugin marketplace; automatic rule pack updates.

**Testing Strategy**: Unit tests written during Phase 16, but manual verification done throughout. Phase 17 is comprehensive validation and bug fixing before release.

**Estimated Timeline**: 8-12 weeks for single developer; 4-6 weeks for small team working in parallel.
