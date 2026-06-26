#Requires -Version 5.1
<#
.SYNOPSIS
    Runs the bill-core backend test suite.

.DESCRIPTION
    Discovers the Python interpreter (virtual env first, then system python),
    then runs pytest against all test_*.py files in the bill-core directory.

.PARAMETER Path
    Optional directory to collect tests from. Defaults to the script's own directory.

.PARAMETER Verbose
    Pass -Verbose to see full pytest output instead of the default quiet summary.

.EXAMPLE
    .\run_backend_tests.ps1
    .\run_backend_tests.ps1 -Verbose
#>
param(
    [string]$Path = "",
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

# Resolve the test directory
if (-not $Path) { $Path = $Root }

# Find python: prefer the local virtual environment
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $Python = "python"
}

Write-Host "=== Bill Core Backend Tests ===" -ForegroundColor Cyan
Write-Host "Root : $Root"
Write-Host "Python: $Python"
Write-Host "Tests : $Path"
Write-Host ""

# Build pytest args
$PytestArgs = @(
    "-m", "pytest",
    $Path,
    "--tb=short"
)
if ($Verbose) {
    $PytestArgs += "-v"
} else {
    $PytestArgs += "-q"
}

# Run
& $Python @PytestArgs
$ExitCode = $LASTEXITCODE

if ($ExitCode -eq 0) {
    Write-Host "`nAll tests passed." -ForegroundColor Green
} else {
    Write-Warning "`nOne or more tests failed (exit code $ExitCode)."
}

exit $ExitCode
