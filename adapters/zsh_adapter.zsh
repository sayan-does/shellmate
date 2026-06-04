#!/bin/zsh
# ShellMate Zsh Adapter
# Install by adding to ~/.zshrc: source ~/.shellmate/hooks/zsh_hook.sh

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
            read "confirmation?  Type 'yes' to proceed: "
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

# If user types a command starting with /s or /a, show a subtle suggestion
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
                    # print a dim, subtle hint
                    echo ""
                    echo -e "\e[36;2m[ShellMate] suggestion: $msg\e[0m"
                fi
            fi
        fi
        # prevent execution: user can edit the line and press enter again
        return 1
    fi
    return 0
}

# Hook into zsh preexec to check prefix
shellmate_preexec() {
    # $1 is the command about to run
    if shellmate_suggest_prefix "$1"; then
        shellmate_analyze "$1"
    else
        # prevent execution by sending SIGINT to the current shell job
        kill -INT $$
    fi
}

# Zsh preexec hook
autoload -Uz add-zsh-hook
shellmate_preexec() {
    shellmate_analyze "$1"
}
add-zsh-hook preexec shellmate_preexec
