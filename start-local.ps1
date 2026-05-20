# Conductor Companion -- local dev launcher
#
# Usage:
#   .\start-local.ps1              Normal start
#   .\start-local.ps1 -ForceDeps  Reinstall all requirements before starting

param([switch]$ForceDeps)

$ErrorActionPreference = 'Stop'
$Root   = $PSScriptRoot
$Log    = "$Root\.hub-logs\app.log"
$LogErr = "$Root\.hub-logs\app.err"

# Create log dir, wipe old logs
New-Item -ItemType Directory -Path "$Root\.hub-logs" -Force | Out-Null
if (Test-Path $Log)    { Remove-Item $Log }
if (Test-Path $LogErr) { Remove-Item $LogErr }

# Activate venv -- create it automatically if missing
$Venv = "$Root\.venv\Scripts\Activate.ps1"
if (-not (Test-Path $Venv)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv "$Root\.venv"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: failed to create .venv. Is Python in PATH?" -ForegroundColor Red
        exit 1
    }
}
. $Venv

# Install deps if requested or venv looks empty
if ($ForceDeps -or (-not (Test-Path "$Root\.venv\Lib\site-packages\flask"))) {
    Write-Host "Installing dependencies..." -ForegroundColor Cyan
    pip install -r "$Root\requirements.txt" --quiet
}

# Copy .env.example if no .env present
if (-not (Test-Path "$Root\.env")) {
    Write-Host "WARNING: .env not found - copying from .env.example" -ForegroundColor Yellow
    Copy-Item "$Root\.env.example" "$Root\.env"
}

# Load .env into process environment so it takes precedence over hub-injected vars
Get-Content "$Root\.env" | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        $key = $matches[1]
        $val = $matches[2].Trim().Trim('"').Trim("'")
        [System.Environment]::SetEnvironmentVariable($key, $val, 'Process')
    }
}

$env:FLASK_DEBUG = if ($env:FLASK_ENV -eq 'production') { '0' } else { '1' }

# Get LAN IP (skip link-local, vEthernet, WSL, loopback)
$IP = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike '169.254.*' -and
                   $_.InterfaceAlias -notlike '*vEthernet*' -and
                   $_.InterfaceAlias -notlike '*WSL*' -and
                   $_.IPAddress -ne '127.0.0.1' } |
    Select-Object -First 1).IPAddress

$Port = if ($env:PORT) { $env:PORT } else { '5000' }
Write-Host "---"
Write-Host "Conductor Companion"
Write-Host "  Port:       $Port"
Write-Host "  Local:      http://localhost:${Port}/health"
if ($IP) { Write-Host "  Network:    http://${IP}:${Port}/health" }
Write-Host "  Conductor:  $env:CONDUCTOR_URL"
Write-Host "  Logs:       $Root\.hub-logs\"
Write-Host "---"
Write-Host "Endpoints:"
Write-Host "  GET  /                              - UI dashboard"
Write-Host "  GET  /api/v1/health                 - Health check"
Write-Host "  GET  /api/v1/search                 - Workflow search"
Write-Host "  GET  /api/v1/workers                - Worker health"
Write-Host "  GET  /api/v1/batches                - Migration batches"
Write-Host "  GET  /api/v1/diff                   - Workflow diff"
Write-Host "  GET  /api/v1/secrets                - Conductor secrets"
Write-Host "  POST /api/v1/reconciler/analyze     - Failure reconciler"
Write-Host "  GET  /api/v1/tracer/:id             - Correlation tracer"
Write-Host "  POST /api/v1/test-harness/run       - Test harness"
Write-Host "  GET  /api/v1/digest/daily           - Performance digest"
Write-Host "  GET  /api/v1/digest/recommendations - Recommendations"
Write-Host "---"

# Continue so Python's stderr logging doesn't trip PowerShell's error handler
$ErrorActionPreference = 'Continue'
python -u "$Root\run.py" >> $Log 2>> $LogErr
