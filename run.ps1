param(
    [string]$PythonExe = 'python',
    [ValidateRange(1, 65535)][int]$Port = 8000,
    [switch]$NoBrowser,
    [switch]$StrictPort
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    $launchArgs = @('run.py', '--port', "$Port")
    if (-not $NoBrowser) { $launchArgs += '--open-browser' }
    if ($StrictPort) { $launchArgs += '--strict-port' }
    if (Test-Path -LiteralPath $localPython) {
        & $localPython @launchArgs
    } else {
        & $PythonExe @launchArgs
    }
    if ($LASTEXITCODE -ne 0) { throw "Career Quest exited with code $LASTEXITCODE" }
} finally {
    Pop-Location
}
