param([string]$PythonExe = 'python')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $localPython) {
        & $localPython run.py
    } else {
        & $PythonExe run.py
    }
    if ($LASTEXITCODE -ne 0) { throw "Career Quest exited with code $LASTEXITCODE" }
} finally {
    Pop-Location
}
