# ShellMate PowerShell Adapter - PSReadLine two-phase annotations
# Install: add to $PROFILE ->  . <path-to>/adapters/powershell_adapter.ps1
# Encoding: ASCII-safe strings for Windows PowerShell 5.1 compatibility

$script:ShellMateRoot = Split-Path -Parent $PSScriptRoot
if (-not $script:ShellMateRoot) {
    $script:ShellMateRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    $script:ShellMateRoot = Split-Path -Parent $script:ShellMateRoot
}

$script:SMTimer = $null
$script:ShellMateLastDangerous = $null
$script:ShellMateNeedsConfirm = $null
$script:ShellMatePython = $null
$script:SMConsequenceShown = $null       # command for which consequence was shown
$script:SMConsequenceRequireConfirm = $null  # command needing second Enter
$script:SMConsequenceConfirmArmed = $null    # set after first Enter blocked
$script:SMConsequenceJob = $null         # background job fetching consequence

function Get-ShellMatePython {
    if ($script:ShellMatePython) { return $script:ShellMatePython }
    $candidates = @("python", "python3", "py")
    foreach ($c in $candidates) {
        $cmd = Get-Command $c -ErrorAction SilentlyContinue
        if ($cmd) {
            $script:ShellMatePython = $cmd.Source
            return $script:ShellMatePython
        }
    }
    return $null
}

function Show-ShellMateAnnotation {
    param(
        [string]$Text,
        [string]$Severity = "MEDIUM"
    )
    if ([string]::IsNullOrWhiteSpace($Text)) { return }

    $ESC = [char]27
    $color = switch ($Severity) {
        "CRITICAL" { "${ESC}[91m" }
        "HIGH" { "${ESC}[91m" }
        "blocking" { "${ESC}[91m" }
        default { "${ESC}[93m" }
    }
    $reset = "${ESC}[0m"

    # Fallback for legacy consoles without VT
    if (-not $env:TERM -and $PSVersionTable.PSVersion.Major -le 5) {
        Write-Host ""
        Write-Host $Text -ForegroundColor Red
        return
    }

    # Save cursor, move down 1, clear line, write, restore - target <2ms
    [Console]::Write("${ESC}[s${ESC}[1B${ESC}[2K${color}${Text}${reset}${ESC}[u")
}

function Show-ShellMateConsequence {
    param(
        [string]$WhatHappens,
        [string]$Scope,
        [string]$Reversible,
        [string]$SuggestedFix = "",
        [string]$Severity = "MEDIUM"
    )
    $ESC = [char]27
    $color = if ($Severity -in @("HIGH","CRITICAL","blocking")) { "${ESC}[91m" } `
             elseif ($Severity -in @("SAFE","LOW")) { "${ESC}[92m" } `
             else { "${ESC}[93m" }
    $reset = "${ESC}[0m"
    # Color scheme mirrors shellmate/ui/colors.py: caution=91 red, warning=93
    # yellow, suggestion/safe=92 green. A suggested fix is a suggestion -> green.
    $green = "${ESC}[92m"

    $line1 = "${color}  -> ${WhatHappens}${reset}"
    $line2 = "${color}  -> Reversible: ${Reversible}  |  ${Scope}${reset}"
    $line3 = if ($SuggestedFix) { "${green}  -> Safe alt: ${SuggestedFix}${reset}" } else { "" }

    # Save cursor, write 3 lines below prompt, restore
    [Console]::Write("${ESC}[s")
    [Console]::Write("${ESC}[1B${ESC}[2K${line1}")
    [Console]::Write("${ESC}[2B${ESC}[2K${line2}")
    if ($line3) { [Console]::Write("${ESC}[3B${ESC}[2K${line3}") }
    [Console]::Write("${ESC}[u")
}

function Clear-ShellMateConsequence {
    $ESC = [char]27
    [Console]::Write("${ESC}[s${ESC}[1B${ESC}[2K${ESC}[2B${ESC}[2K${ESC}[3B${ESC}[2K${ESC}[u")
}

function Invoke-ShellMateConsequenceAsync {
    param([string]$Command)

    # Show placeholder immediately
    $ESC = [char]27
    [Console]::Write("${ESC}[s${ESC}[1B${ESC}[2K${ESC}[90m  [?] Analyzing...${ESC}[0m${ESC}[u")

    # Stop any previous consequence job
    if ($script:SMConsequenceJob) {
        Stop-Job $script:SMConsequenceJob -ErrorAction SilentlyContinue
        Remove-Job $script:SMConsequenceJob -Force -ErrorAction SilentlyContinue
        $script:SMConsequenceJob = $null
    }

    $py = Get-ShellMatePython
    $client = Get-ShellMateClientPath
    $capturedCmd = $Command

    $script:SMConsequenceJob = Start-Job -ScriptBlock {
        param($py, $client, $cmd)
        try {
            $raw = & $py $client $cmd 2>$null | Out-String
            if ($raw) { return ($raw | ConvertFrom-Json) }
        } catch {}
        return $null
    } -ArgumentList $py, $client, $capturedCmd
}

function Invoke-ShellMateInstantCheck {
    param([string]$Command)
    $py = Get-ShellMatePython
    if (-not $py) { return $null }

    $matcher = Join-Path $script:ShellMateRoot "rules\catastrophic_matcher.py"
    if (-not (Test-Path $matcher)) {
        $matcher = Join-Path $PSScriptRoot "..\rules\catastrophic_matcher.py"
    }

    try {
        $json = & $py $matcher $Command 2>$null | Out-String
        if ($json) {
            return ($json | ConvertFrom-Json)
        }
    } catch {}
    return $null
}

function Start-ShellMateDebounce {
    param([string]$Command)

    if ($script:SMTimer) {
        $script:SMTimer.Stop()
        $script:SMTimer.Dispose()
        $script:SMTimer = $null
    }

    $py = Get-ShellMatePython
    if (-not $py) { return }

    $client = Join-Path $script:ShellMateRoot "ipc\ps_client.py"
    if (-not (Test-Path $client)) {
        $client = Join-Path $PSScriptRoot "..\ipc\ps_client.py"
    }

    $script:SMTimer = [System.Timers.Timer]::new(300)
    $script:SMTimer.AutoReset = $false
    $capturedCmd = $Command
    $capturedPy = $py
    $capturedClient = $client
    $script:SMTimer.add_Elapsed({
        try {
            $raw = & $capturedPy $capturedClient $capturedCmd 2>$null | Out-String
            if ($raw) {
                $result = $raw | ConvertFrom-Json
                if ($result.annotation) {
                    $sev = if ($result.severity) { $result.severity } else { "MEDIUM" }
                    Show-ShellMateAnnotation -Text $result.annotation -Severity $sev
                }
            }
        } catch {}
    }.GetNewClosure())
    $script:SMTimer.Start()
}

function Stop-ShellMateDebounce {
    if ($script:SMTimer) {
        $script:SMTimer.Stop()
        $script:SMTimer.Dispose()
        $script:SMTimer = $null
    }
}

# Enter key interception - Tier 1 instant block, Tier 2 accept + debounce
try {
    Set-PSReadLineKeyHandler -Key Enter -ScriptBlock {
        param($key, $arg)

        $command = $null
        $cursor = $null
        [Microsoft.PowerShell.PSConsoleReadLine]::GetBufferState([ref]$command, [ref]$cursor)

        if ([string]::IsNullOrWhiteSpace($command)) {
            [Microsoft.PowerShell.PSConsoleReadLine]::AcceptLine()
            return
        }

        # Tier 1: Instant catastrophic check
        $instant = Invoke-ShellMateInstantCheck -Command $command
        if ($instant -and $instant.matched) {
            $msg = if ($instant.message) { $instant.message } else { "BLOCKING - dangerous command" }
            Show-ShellMateAnnotation -Text ("[!] BLOCKING - " + $msg) -Severity blocking

            # Double-tap confirm: first Enter blocks, second allows
            if ($script:ShellMateLastDangerous -ne $command) {
                $script:ShellMateLastDangerous = $command
                $script:ShellMateNeedsConfirm = $command
                return  # Suppress Enter
            }
            # Second Enter - allow through
            $script:ShellMateLastDangerous = $null
            $script:ShellMateNeedsConfirm = $null
        }

        Stop-ShellMateDebounce

        # Consequence gate: HIGH/CRITICAL commands need second Enter after preview
        if ($script:SMConsequenceRequireConfirm -and $script:SMConsequenceRequireConfirm -eq $command) {
            if ($script:SMConsequenceConfirmArmed -ne $command) {
                $script:SMConsequenceConfirmArmed = $command
                Show-ShellMateAnnotation -Text "[Press Enter again to execute]" -Severity blocking
                return  # Suppress first Enter
            }
            $script:SMConsequenceRequireConfirm = $null
            $script:SMConsequenceConfirmArmed = $null
            # Second Enter — allow execution
        } else {
            $script:SMConsequenceConfirmArmed = $null
        }
        Clear-ShellMateConsequence
        $script:SMConsequenceShown = $null

        Start-ShellMateDebounce $command
        [Microsoft.PowerShell.PSConsoleReadLine]::AcceptLine()
    }
} catch {
    Write-Verbose "ShellMate: PSReadLine Enter hook unavailable: $_"
}

# Also expose analysis helper for non-PSReadLine hosts
function Invoke-ShellMateAnalysis {
    param([string]$Command)
    if ([string]::IsNullOrWhiteSpace($Command)) { return }

    $instant = Invoke-ShellMateInstantCheck -Command $Command
    if ($instant -and $instant.matched) {
        Show-ShellMateAnnotation -Text ("[!] BLOCKING - " + $instant.message) -Severity blocking
        return
    }

    $py = Get-ShellMatePython
    $client = Join-Path $script:ShellMateRoot "ipc\ps_client.py"
    if ($py -and (Test-Path $client)) {
        try {
            $raw = & $py $client $Command 2>$null | Out-String
            $result = $raw | ConvertFrom-Json
            if ($result.annotation) {
                Show-ShellMateAnnotation -Text $result.annotation -Severity $result.severity
            }
        } catch {}
    }
}

function Get-ShellMateClientPath {
    $client = Join-Path $script:ShellMateRoot "ipc\ps_client.py"
    if (-not (Test-Path $client)) {
        $client = Join-Path $PSScriptRoot "..\ipc\ps_client.py"
    }
    return $client
}

function Invoke-ShellMateComplete {
    param([string]$Prefix)
    $py = Get-ShellMatePython
    $client = Get-ShellMateClientPath
    if (-not $py -or -not (Test-Path $client)) { return @() }
    try {
        $raw = & $py $client "--complete" $Prefix 2>$null | Out-String
        if (-not $raw) { return @() }
        $result = $raw | ConvertFrom-Json
        if ($result.completions) { return @($result.completions) }
    } catch {}
    return @()
}

# --- Step 3.5: Ghost text (PS 7.2+ predictor) or Tab fallback (PS 5.1) ---
$script:ShellMatePredictorRegistered = $false
$script:SMLastSuggestion = $null
$script:SMLastPrefix = $null

$psrl = Get-Module PSReadLine -ErrorAction SilentlyContinue
$canPredict = (
    $PSVersionTable.PSVersion -ge [Version]"7.2" -and
    $null -ne $psrl -and
    $psrl.Version -ge [Version]"2.1"
)

if ($canPredict) {
    $predictorFile = Join-Path $PSScriptRoot "powershell_predictor.ps1"
    if (Test-Path $predictorFile) {
        # Guard against predictor load/compile failures (e.g. prediction-API
        # drift across PS builds) so the adapter still loads and the Tab
        # ghost-text fallback below can engage instead of spewing errors.
        try { . $predictorFile } catch { Write-Verbose "ShellMate: predictor load failed: $_" }
    }
}

# Path B: Tab override ghost-text when predictor is unavailable
if (-not $script:ShellMatePredictorRegistered) {
    try {
        Set-PSReadLineKeyHandler -Key Tab -ScriptBlock {
            param($key, $arg)
            $line = $null; $cursor = $null
            [Microsoft.PowerShell.PSConsoleReadLine]::GetBufferState([ref]$line, [ref]$cursor)
            if ($null -eq $line) { $line = "" }
            $prefix = if ($cursor -gt 0 -and $cursor -le $line.Length) { $line.Substring(0, $cursor) } else { $line }

            # Second Tab: suggestion cached → accept + show consequence
            if ($script:SMLastPrefix -eq $prefix -and $script:SMLastSuggestion) {
                $accepted = $script:SMLastSuggestion
                [Microsoft.PowerShell.PSConsoleReadLine]::Replace(0, $line.Length, $accepted)
                $script:SMLastSuggestion = $null
                $script:SMLastPrefix = $null
                $script:SMConsequenceShown = $accepted

                # Fetch consequence in background
                Invoke-ShellMateConsequenceAsync -Command $accepted

                # Poll job for up to 1.5s then render
                $deadline = [DateTime]::Now.AddSeconds(1.5)
                while ([DateTime]::Now -lt $deadline) {
                    Start-Sleep -Milliseconds 80
                    if ($script:SMConsequenceJob -and $script:SMConsequenceJob.State -ne 'Running') {
                        $result = Receive-Job $script:SMConsequenceJob -ErrorAction SilentlyContinue
                        Remove-Job $script:SMConsequenceJob -Force -ErrorAction SilentlyContinue
                        $script:SMConsequenceJob = $null
                        if ($result) {
                            $cp = $result.consequence_preview
                            if ($cp) {
                                $rev = if ($cp.reversible) { "Yes" } else { "No" }
                                $sev = if ($result.severity) { $result.severity } else { "MEDIUM" }
                                Show-ShellMateConsequence `
                                    -WhatHappens $cp.what_happens `
                                    -Scope $cp.scope `
                                    -Reversible $rev `
                                    -SuggestedFix $cp.suggested_fix `
                                    -Severity $sev
                                if ($sev -in @("HIGH","CRITICAL","blocking")) {
                                    $script:SMConsequenceRequireConfirm = $accepted
                                }
                            }
                        }
                        break
                    }
                }
                return
            }

            # First Tab: get completions, show ghost text
            $script:SMLastSuggestion = $null
            $script:SMLastPrefix = $null
            try {
                $completions = @(Invoke-ShellMateComplete -Prefix $prefix)
                $suggestion = $completions | Select-Object -First 1
                if ($suggestion -and $suggestion -ne $prefix) {
                    $script:SMLastSuggestion = [string]$suggestion
                    $script:SMLastPrefix = $prefix
                    $ESC = [char]27
                    $suffix = ([string]$suggestion).Substring([Math]::Min($prefix.Length, ([string]$suggestion).Length))
                    if ($suffix) {
                        # Autocomplete ghost-text is a suggestion -> green (92),
                        # matching shellmate/ui/colors.py.
                        [Console]::Write("${ESC}[92m${suffix}${ESC}[0m")
                        [Console]::Write("${ESC}[$($suffix.Length)D")
                    }
                    return
                }
            } catch {}
            [Microsoft.PowerShell.PSConsoleReadLine]::MenuComplete()
        }
    } catch {
        Write-Verbose "ShellMate: Tab ghost-text handler unavailable: $_"
    }
}

# --- Step 3.6: Native argument completer (optional augment) ---
# Requires -CommandName; bare -Native prompts interactively in PS and hangs sourcing.
# Tab handler + predictor already cover ShellMate completions — skip global native
# registration unless a curated command list is provided via env.
$smNativeCmds = $env:SM_NATIVE_COMPLETERS
if ($smNativeCmds) {
    $names = @($smNativeCmds -split '[,; ]+' | Where-Object { $_ })
    if ($names.Count -gt 0) {
        try {
            Register-ArgumentCompleter -Native -CommandName $names -ScriptBlock {
                param(
                    [string]$wordToComplete,
                    [System.Management.Automation.Language.CommandAst]$commandAst,
                    [int]$cursorPosition
                )

                $fullLine = $commandAst.Extent.Text
                try {
                    $completions = @(Invoke-ShellMateComplete -Prefix $fullLine)
                    foreach ($c in $completions) {
                        [System.Management.Automation.CompletionResult]::new(
                            [string]$c,
                            [string]$c,
                            "ParameterValue",
                            ("ShellMate: " + [string]$c)
                        )
                    }
                } catch {}
            }
        } catch {
            Write-Verbose "ShellMate: ArgumentCompleter registration unavailable: $_"
        }
    }
}
