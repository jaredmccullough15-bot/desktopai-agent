$ErrorActionPreference = 'Stop'

$repo = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($repo) -and $PSCommandPath) {
    $repo = Split-Path -Parent $PSCommandPath
}
if ([string]::IsNullOrWhiteSpace($repo) -and $MyInvocation.MyCommand.Path) {
    $repo = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if ([string]::IsNullOrWhiteSpace($repo)) {
    throw "Could not resolve script folder."
}

$repo = (Resolve-Path -Path $repo).Path
$launcher = Join-Path $repo "run_worker_ui.cmd"
if (!(Test-Path $launcher)) {
    throw "run_worker_ui.cmd not found at $launcher"
}

$desktop = [Environment]::GetFolderPath('Desktop')
if ([string]::IsNullOrWhiteSpace($desktop) -or !(Test-Path $desktop)) {
    throw "Desktop path is unavailable."
}

$shortcutPath = Join-Path $desktop "Jarvis Worker.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcher
$shortcut.WorkingDirectory = $repo
$shortcut.WindowStyle = 1
$shortcut.IconLocation = "shell32.dll,21"
$shortcut.Description = "Launch Jarvis Worker UI"
$shortcut.Save()

Write-Host "Created desktop shortcut: $shortcutPath" -ForegroundColor Green
