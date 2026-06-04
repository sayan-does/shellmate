# ShellMate User Flow Demonstration

## Overview
This document demonstrates the complete user flow for ShellMate - an Intelligent Command Safety Layer for Modern Terminals.

---

## 1. Initial Setup - View Available Commands

```bash
$ shellmate --help
```

**Output:**
```
ShellMate - Intelligent Command Safety Layer for Modern Terminals

Commands:
  analyze       Analyze a shell command for safety
  cache         Manage ShellMate semantic cache
  config        View or edit ShellMate configuration
  configure     Configure API credentials for AI providers
  disable       Disable ShellMate daemon and command interception
  doctor        Run environment diagnostics
  enable        Enable ShellMate daemon and command interception
  install       Install ShellMate and shell hooks
  logs          Tail ShellMate daemon logs
  providers     List configured AI providers
  status        Show ShellMate daemon and provider status
  uninstall     Remove ShellMate and all hooks
  update-rules  Validate and reload local rule packs
```

---

## 2. Environment Detection

```bash
$ shellmate doctor
```

**Output:**
```json
{
  "os": "windows",
  "shell": "cmd",
  "environment": "native",
  "terminal": "kiro"
}
```

**What it does:** Detects your operating system, shell type, execution environment, and terminal emulator.

---

## 3. Check Configuration

```bash
$ shellmate config
```

**Output:**
```json
{
  "credentials": {
    "GROQ_API_KEY": {
      "configured": true,
      "key": "gsk_************************************************ZwnH"
    },
    "OPENROUTER_API_KEY": {
      "configured": true,
      "key": "sk-o*****************************************************************4c8b"
    },
    "CONTEXT7_API_KEY": {
      "configured": true,
      "key": "ctx7***********************************524f"
    }
  },
  "settings": {
    "daemon": {
      "host": "127.0.0.1",
      "port": 9823,
      "socket_path": "C:\\Users\\defau/.shellmate\\shellmate.sock",
      "pipe_name": "\\\\.\\pipe\\shellmate"
    },
    "cache": {
      "enabled": true,
      "backend": "faiss",
      "model": "all-MiniLM-L6-v2",
      "similarity_threshold": 0.92,
      "expiration_days": 30,
      "max_entries": 10000
    },
    "providers": {
      "risk_analysis": {
        "primary": "groq",
        "model": "llama-3.3-70b-versatile"
      },
      "remediation": {
        "primary": "openrouter",
        "model": "gpt-4o-mini",
        "fallbacks": [
          "meta-llama/llama-3.3-70b-instruct",
          "qwen/qwen2.5-72b-instruct"
        ]
      }
    },
    "latency_targets": {
      "cache_hit_ms": 200,
      "rule_match_ms": 50,
      "ai_analysis_ms": 5000
    }
  }
}
```

**What it shows:**
- ✅ All 3 API keys are configured (Groq, OpenRouter, Context7)
- 🏗️ Daemon settings (host, port, socket paths)
- 💾 Cache configuration (FAISS-powered semantic cache)
- 🤖 AI provider settings with fallback models
- ⚡ Performance targets

---

## 4. Check AI Provider Status

```bash
$ shellmate providers
```

**Output:**
```json
{
  "groq": {
    "configured": true,
    "status": "available"
  },
  "openrouter": {
    "configured": true,
    "status": "available",
    "fallback_models": [
      "meta-llama/llama-3.3-70b-instruct",
      "qwen/qwen2.5-72b-instruct"
    ]
  }
}
```

**What it shows:**
- ✅ Groq is configured and available (for risk analysis)
- ✅ OpenRouter is configured with 2 fallback models (for remediation)

---

## 5. Check Daemon Status

```bash
$ shellmate status
```

**Output:**
```json
{
  "status": "stopped",
  "pid": null,
  "providers": {
    "groq": {
      "configured": true,
      "status": "available"
    },
    "openrouter": {
      "configured": true,
      "status": "available",
      "fallback_models": [...]
    }
  }
}
```

**What it shows:**
- ⏸️ Daemon is currently stopped
- 📊 Provider status included in output

---

## 6. Detailed Diagnostics

```bash
$ shellmate doctor --verbose
```

**Output:**
```json
{
  "environment": {
    "os": "windows",
    "shell": "cmd",
    "environment": "native",
    "terminal": "kiro"
  },
  "daemon": {
    "status": "stopped",
    "pid": null
  },
  "providers": {
    "groq": {
      "configured": true,
      "status": "available"
    },
    "openrouter": {
      "configured": true,
      "status": "available",
      "fallback_models": [...]
    }
  },
  "metrics": {
    "error": "No metrics data available"
  }
}
```

**What it shows:**
- 🔍 Complete health report including environment, daemon, providers, and metrics
- ℹ️ No metrics yet since daemon hasn't been running

---

## 7. Analyze Commands (Requires Daemon)

```bash
$ shellmate analyze "echo 'Hello World'"
```

**Output:**
```
Error: Connection refused. Run 'shellmate enable' first.
```

**What happens:**
- 🚫 Command analysis requires the daemon to be running
- 💡 User is prompted to enable the daemon first

---

## Complete User Workflow

### First-Time User Journey:

1. **Install ShellMate** → `pip install shellmate`
2. **Check environment** → `shellmate doctor`
3. **Configure credentials** → `shellmate configure`
4. **Install shell hooks** → `shellmate install`
5. **Enable daemon** → `shellmate enable`
6. **Verify status** → `shellmate status`
7. **Analyze commands** → `shellmate analyze "rm -rf /"`

### Daily Usage:

1. ShellMate runs in the background
2. Intercepts commands before execution
3. Analyzes for safety (rules + AI)
4. Provides warnings and alternatives for dangerous commands
5. Caches results for fast repeated analysis

---

## Key Features Demonstrated

✅ **Environment Detection** - Automatically detects OS, shell, terminal  
✅ **Configuration Management** - Easy credential and settings management  
✅ **Provider Status** - Real-time AI provider availability  
✅ **Health Diagnostics** - Comprehensive system health checks  
✅ **Daemon Architecture** - Background service for command interception  
✅ **Safety Analysis** - Multi-layer command risk assessment  

---

## Next Steps

To see the full analysis in action:
1. Start the daemon: `shellmate enable`
2. Analyze a safe command: `shellmate analyze "ls -la"`
3. Analyze a dangerous command: `shellmate analyze "rm -rf /"`
4. View metrics: `shellmate doctor --verbose`
5. Check logs: `shellmate logs`

---

## Architecture Overview

```
User Command → Shell Hook → ShellMate Daemon → Analysis Pipeline
                                                    ├── Environment Detector
                                                    ├── Command Parser
                                                    ├── Typo Detector
                                                    ├── Rule Engine (30+ rules)
                                                    ├── Semantic Cache (FAISS)
                                                    ├── AI Risk Analysis (Groq)
                                                    └── AI Remediation (OpenRouter)
                                                    
                                                  ↓
                               User Prompt ← Risk Level + Alternatives
```

