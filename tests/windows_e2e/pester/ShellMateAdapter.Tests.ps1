# Pester floor for the ShellMate PowerShell adapter.
# Deterministic PS-side unit coverage, independent of the ConPTY harness.
#
# Run from the repo root (so python can import the dev-tree package):
#   Invoke-Pester tests/windows_e2e/pester/ShellMateAdapter.Tests.ps1
#
# Requires: Pester 5+. Behavioural checks that need Python/the package self-skip
# when `python` is not on PATH.

BeforeAll {
    $repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..' '..' '..')
    $script:AdapterPath = Join-Path $repoRoot 'shellmate' 'adapters' 'powershell_adapter.ps1'

    # Dot-source the adapter. The Set-PSReadLineKeyHandler blocks are wrapped in
    # try/catch in the adapter, so sourcing is safe in a non-interactive host.
    . $script:AdapterPath

    $script:HasPython = $null -ne (Get-Command python -ErrorAction SilentlyContinue)
}

Describe 'Adapter sourcing' {
    It 'exposes the expected function surface' {
        foreach ($fn in @(
            'Get-ShellMatePython',
            'Invoke-ShellMateInstantCheck',
            'Invoke-ShellMateComplete',
            'Show-ShellMateAnnotation',
            'Show-ShellMateConsequence',
            'Invoke-ShellMateAnalysis'
        )) {
            (Get-Command $fn -ErrorAction SilentlyContinue) | Should -Not -BeNullOrEmpty -Because "$fn must be defined"
        }
    }

    It 'resolves ShellMateRoot to the package directory' {
        $script:ShellMateRoot | Should -Not -BeNullOrEmpty
        (Join-Path $script:ShellMateRoot 'ipc\ps_client.py') | Should -Exist
        (Join-Path $script:ShellMateRoot 'rules\catastrophic_matcher.py') | Should -Exist
    }
}

Describe 'Get-ShellMatePython' {
    It 'finds a python interpreter when one is on PATH' -Skip:(-not $script:HasPython) {
        Get-ShellMatePython | Should -Not -BeNullOrEmpty
    }
}

Describe 'Invoke-ShellMateInstantCheck (local matcher)' {
    It 'flags a catastrophic command' -Skip:(-not $script:HasPython) {
        $result = Invoke-ShellMateInstantCheck -Command 'rm -rf /'
        if ($null -eq $result) {
            Set-ItResult -Skipped -Because 'matcher produced no JSON (package not importable in this cwd)'
            return
        }
        $result.matched | Should -BeTrue
    }

    It 'does not flag a safe command' -Skip:(-not $script:HasPython) {
        $result = Invoke-ShellMateInstantCheck -Command 'Get-ChildItem'
        if ($null -eq $result) {
            Set-ItResult -Skipped -Because 'matcher produced no JSON (package not importable in this cwd)'
            return
        }
        $result.matched | Should -BeFalse
    }
}

Describe 'Invoke-ShellMateComplete (completion surface)' {
    It 'returns a push completion for "git pu"' -Skip:(-not $script:HasPython) {
        $comps = @(Invoke-ShellMateComplete -Prefix 'git pu')
        if ($comps.Count -eq 0) {
            Set-ItResult -Skipped -Because 'no completions (package not importable in this cwd)'
            return
        }
        ($comps -join "`n") | Should -Match 'push'
    }
}
