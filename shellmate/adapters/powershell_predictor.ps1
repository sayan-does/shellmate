# ShellMate PowerShell Prediction Source (PS 7.2+ / PSReadLine 2.1+)
# Sourced only when version checks pass — keeps powershell_adapter.ps1 parseable on 5.1

class ShellMatePredictor : System.Management.Automation.Subsystem.Prediction.ICommandPredictor {
    [System.Guid] $Id = [System.Guid]::new("d8f1b5a2-4c3e-4f7d-9a8b-1e2f3c4d5e6f")
    [string] $Name = "ShellMate"
    [string] $Description = "Context-aware command suggestions"
    [string] $PythonPath
    [string] $ClientPath

    ShellMatePredictor([string]$PythonPath, [string]$ClientPath) {
        $this.PythonPath = $PythonPath
        $this.ClientPath = $ClientPath
    }

    [bool] CanAcceptFeedback(
        [System.Management.Automation.Subsystem.Prediction.PredictionClient] $client,
        [System.Management.Automation.Subsystem.Prediction.PredictorFeedbackKind] $feedback
    ) { return $false }

    [void] OnSuggestionDisplayed(
        [System.Management.Automation.Subsystem.Prediction.PredictionClient] $client,
        [uint] $session,
        [int] $countOrIndex
    ) {}

    [void] OnSuggestionAccepted(
        [System.Management.Automation.Subsystem.Prediction.PredictionClient] $client,
        [uint] $session,
        [string] $acceptedSuggestion
    ) {}

    [void] OnCommandLineAccepted(
        [System.Management.Automation.Subsystem.Prediction.PredictionClient] $client,
        [System.Collections.Generic.IReadOnlyList[string]] $history
    ) {}

    [void] OnCommandLineExecuted(
        [System.Management.Automation.Subsystem.Prediction.PredictionClient] $client,
        [string] $commandLine,
        [bool] $success
    ) {}

    [System.Management.Automation.Subsystem.Prediction.SuggestionPackage] GetSuggestion(
        [System.Management.Automation.Subsystem.Prediction.PredictionClient] $client,
        [System.Management.Automation.Subsystem.Prediction.PredictionContext] $context,
        [System.Threading.CancellationToken] $cancellationToken
    ) {
        $input = $context.InputAst.Extent.Text
        if ([string]::IsNullOrWhiteSpace($input) -or $input.Length -lt 3) {
            return [System.Management.Automation.Subsystem.Prediction.SuggestionPackage]::new(@())
        }

        try {
            if (-not $this.PythonPath -or -not (Test-Path $this.ClientPath)) {
                return [System.Management.Automation.Subsystem.Prediction.SuggestionPackage]::new(@())
            }
            $raw = & $this.PythonPath $this.ClientPath "--complete" $input 2>$null | Out-String
            if (-not $raw) {
                return [System.Management.Automation.Subsystem.Prediction.SuggestionPackage]::new(@())
            }
            $result = $raw | ConvertFrom-Json
            if (-not $result.completions) {
                return [System.Management.Automation.Subsystem.Prediction.SuggestionPackage]::new(@())
            }
            $suggestions = @(
                $result.completions | ForEach-Object {
                    [System.Management.Automation.Subsystem.Prediction.PredictiveSuggestion]::new([string]$_)
                }
            )
            return [System.Management.Automation.Subsystem.Prediction.SuggestionPackage]::new($suggestions)
        } catch {
            return [System.Management.Automation.Subsystem.Prediction.SuggestionPackage]::new(@())
        }
    }
}

$py = Get-ShellMatePython
$client = Join-Path $script:ShellMateRoot "ipc\ps_client.py"
if (-not (Test-Path $client)) {
    $client = Join-Path $PSScriptRoot "..\ipc\ps_client.py"
}

if ($py -and (Test-Path $client)) {
    try {
        $predictor = [ShellMatePredictor]::new($py, $client)
        [System.Management.Automation.Subsystem.SubsystemManager]::RegisterSubsystem(
            [System.Management.Automation.Subsystem.SubsystemKind]::CommandPredictor,
            $predictor
        )
        Set-PSReadLineOption -PredictionSource Plugin -PredictionViewStyle InlineView -ErrorAction SilentlyContinue
        $script:ShellMatePredictorRegistered = $true
    } catch {
        Write-Verbose "ShellMate: predictor registration failed: $_"
        $script:ShellMatePredictorRegistered = $false
    }
}
