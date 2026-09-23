param(
    [string]$PythonExe = 'python',
    [ValidateRange(1, 65535)][int]$Port = 8000
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $localPython) {
        & $localPython run.py --port $Port
    } else {
        & $PythonExe run.py --port $Port
    }
    if ($LASTEXITCODE -ne 0) { throw "Career Quest exited with code $LASTEXITCODE" }
} finally {
    Pop-Location
}
