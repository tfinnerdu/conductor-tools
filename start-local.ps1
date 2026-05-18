# Conductor Companion - Local Development Startup Script
# Wipe log files
if (Test-Path "app.log") { Remove-Item "app.log" -Force }
if (Test-Path "app.log.err") { Remove-Item "app.log.err" -Force }

# Load environment from .env if present
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^\s*([^#][^=]+)=(.*)$") {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

# Set FLASK_DEBUG via if/else
if ($env:FLASK_DEBUG -eq "true") {
    $env:FLASK_DEBUG = "1"
} else {
    $env:FLASK_DEBUG = "0"
}

Write-Host "Starting Conductor Companion..."
Write-Host "CONDUCTOR_URL: $env:CONDUCTOR_URL"

# Run health check after startup (optional smoke test)
# curl.exe -s http://localhost:5000/health

# Start the app unbuffered
python -u run.py 2>&1 | Tee-Object -FilePath "app.log"
