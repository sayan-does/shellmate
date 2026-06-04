#!/bin/bash
# ShellMate Bash Adapter
# Install by adding to ~/.bashrc: source ~/.shellmate/hooks/bash_hook.sh

SHELLMATE_LAST_COMMAND=""

shellmate_preexec() {
    SHELLMATE_LAST_COMMAND="$1"
}

shellmate_precmd() {
    if [ -n "$SHELLMATE_LAST_COMMAND" ]; then
        local cmd="$SHELLMATE_LAST_COMMAND"
        SHELLMATE_LAST_COMMAND=""
        shellmate_analyze "$cmd"
    fi
}

shellmate_analyze() {
    local cmd="$*"
    [ -z "$cmd" ] && return

    local result
    result=$(shellmate analyze --quiet "$cmd" 2>/dev/null)
    local exit_code=$?

    if [ $exit_code -ne 0 ] && [ -n "$result" ]; then
        local risk=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('risk',''))" 2>/dev/null)

        if [ "$risk" = "CRITICAL" ]; then
            echo ""
            echo "  [ShellMate] CRITICAL: This command is dangerous!"
            local msg=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('message',''))" 2>/dev/null)
            [ -n "$msg" ] && echo "  $msg"
            echo ""
            read -p "  Type 'yes' to proceed: " confirmation
            if [ "$confirmation" != "yes" ] && [ "$confirmation" != "y" ]; then
                echo "  Command cancelled."
                kill -INT $$
            fi
        elif [ "$risk" = "HIGH" ] || [ "$risk" = "MEDIUM" ]; then
            echo ""
            echo "  [ShellMate] $risk warning:"
            local msg=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('message',''))" 2>/dev/null)
            [ -n "$msg" ] && echo "  $msg"
            echo ""
        fi
    fi
}

# If user prefixes a command with /s or /a, show a subtle suggestion and
# prevent immediate execution so they can edit/accept the command.
shellmate_suggest_prefix() {
    local line="$1"
    if [[ "$line" =~ ^(/s|/a)[[:space:]]*(.*) ]]; then
        local payload="${BASH_REMATCH[2]}"
        if [ -n "$payload" ]; then
            local result
            result=$(shellmate analyze --quiet "$payload" 2>/dev/null)
            if [ -n "$result" ]; then
                local msg
                msg=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('message') or d.get('explanation') or (d.get('alternatives') or [''])[0])" 2>/dev/null)
                if [ -n "$msg" ]; then
                    echo ""
                    # dim cyan suggestion
                    echo -e "\e[36;2m[ShellMate] suggestion: $msg\e[0m"
                fi
            fi
        fi
        return 1
    fi
    return 0
}

# Hook into Bash
if [ -n "$BASH_VERSION" ]; then
    preexec_invoke_exec() {
        [ -n "$COMP_LINE" ] && return
        if [ -n "$BASH_COMMAND" ]; then
            if shellmate_suggest_prefix "$BASH_COMMAND"; then
                shellmate_preexec "$BASH_COMMAND"
            else
                # Prevent execution so user can edit
                kill -INT $$
            fi
        fi
    }

    precmd_invoke_exec() {
        shellmate_precmd
    }

    # Install hooks
    DEBUG_BEGIN="preexec_invoke_exec"
    DEBUG_END="precmd_invoke_exec"

    if [ -z "$PROMPT_COMMAND" ]; then
        PROMPT_COMMAND="shellmate_precmd"
    else
        PROMPT_COMMAND="shellmate_precmd; $PROMPT_COMMAND"
    fi

    trap 'shellmate_preexec "$BASH_COMMAND"' DEBUG
fi
