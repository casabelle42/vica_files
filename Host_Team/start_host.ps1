# Run the LAS-VICA Host GUI with lab MQTT broker defaults.
# Usage: .\start_host.ps1
# Optional overrides: VICA_MQTT_BROKER, VICA_MQTT_PORT

$ErrorActionPreference = "Stop"

# Script lives in Host_Team/; resolve absolute paths from here.
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$App = Join-Path $Root "Host\gui\s1_start_app.py"

# Lab broker defaults — only set when the env var is unset (do not clobber overrides).
if (-not $env:VICA_MQTT_BROKER) {
    $env:VICA_MQTT_BROKER = "10.148.1.35"
}
if (-not $env:VICA_MQTT_PORT) {
    $env:VICA_MQTT_PORT = "1884"
}

Write-Host "VICA_MQTT_BROKER=$($env:VICA_MQTT_BROKER)"
Write-Host "VICA_MQTT_PORT=$($env:VICA_MQTT_PORT)"
Write-Host "Starting Host GUI: $App"

# Prefer `python` on Windows; fall back to `py -3` if needed.
$Python = Get-Command python -ErrorAction SilentlyContinue
if ($Python) {
    & python $App
} else {
    & py -3 $App
}
