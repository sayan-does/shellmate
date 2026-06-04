# ShellMate PowerShell Adapter
# Install by adding to $PROFILE: . ~\.shellmate\hooks\powershell_hook.ps1

$script:ShellMateLastCommand = $null

function Invoke-ShellMateAnalysis {
    param([string]$Command)

    if ([string]::IsNullOrWhiteSpace($Command)) { return }

    $result = & shellmate analyze --quiet $Command 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0 -and $result) {
        try {
            $parsed = $result | ConvertFrom-Json
            $risk = $parsed.risk

            if ($risk -eq "CRITICAL") {
                Write-Host ""
                Write-Host "  [ShellMate] CRITICAL: This command is dangerous!" -ForegroundColor Red
                if ($parsed.message) { Write-Host "  $($parsed.message)" -ForegroundColor Yellow }
                Write-Host ""
                $confirmation = Read-Host "  Type 'yes' to proceed"
                if ($confirmation -ne "yes" -and $confirmation -ne "y") {
                    Write-Host "  Command cancelled." -ForegroundColor Yellow
                    throw "ShellMate: Command cancelled by user"
                }
            }
            elseif ($risk -eq "HIGH" -or $risk -eq "MEDIUM") {
                Write-Host ""
                Write-Host "  [ShellMate] $risk warning:" -ForegroundColor Yellow
                if ($parsed.message) { Write-Host "  $($parsed.message)" -ForegroundColor Yellow }
                Write-Host ""
            }
        }
        catch {
            if ($_.Exception.Message -match "ShellMate: Command cancelled") {
                throw
            }
        }
    }
}

# If the user prefixes a command with /s or /a, show a subtle suggestion and
# prevent immediate execution so they can edit/accept the command.
function Invoke-ShellMateSuggestion {
    param([string]$Command)

    if ([string]::IsNullOrWhiteSpace($Command)) { return }

    # Remove leading prefix (/s or /a) and optional space
    $trimmed = $Command -replace '^(?:/s|/a)\s*', ''
    if ([string]::IsNullOrWhiteSpace($trimmed)) { return }

    $result = & shellmate analyze --quiet $trimmed 2>&1 | Out-String
    if ($result) {
        try {
            $parsed = $result | ConvertFrom-Json
            $msg = $parsed.message
            if (-not $msg) { $msg = $parsed.explanation }
            if (-not $msg -and $parsed.alternatives) { $msg = $parsed.alternatives[0] }

            if ($msg) {
                # Dim cyan output for subtle hint
                Write-Host "`n[ShellMate] suggestion: $msg" -ForegroundColor Cyan
            }
        } catch { }
    }
}

# Override PSConsoleHostReadLine for PSReadLine
$global:ShellMateOriginalReadLine = $function:PSConsoleHostReadLine

function Global:PSConsoleHostReadLine {
    $command = [Microsoft.PowerShell.PSConsoleReadLine]::ReadLine()
    if ($command) {
        try {
            Invoke-ShellMateAnalysis -Command $command
        }
        catch {
            # Command was cancelled, clear the input
            return ""
        }
    }
    return $command
}

# Also hook into Set-PSReadLineOption for newer PowerShell versions
try {
    Set-PSReadLineOption -AddToHistoryHandler {
        param($command)
        if ($command) {
            Invoke-ShellMateAnalysis -Command $command
        }
        return $true
    } -ErrorAction SilentlyContinue
}
catch {}
