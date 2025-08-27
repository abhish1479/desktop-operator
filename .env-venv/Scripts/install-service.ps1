param(
  [string]$Name = "DesktopOperator",
  [string]$Python = ".\.venv\Scripts\python.exe",
  [string]$Module = "uvicorn",
  [string]$App = "apps.orchestrator.main:app",
  [int]$Port = 8000
)

$WorkDir = (Get-Location).Path
$Args = "$Module $App --host 127.0.0.1 --port $Port"

# Requires NSSM (Non-Sucking Service Manager) preinstalled and on PATH
nssm install $Name "$Python" $Args
nssm set $Name AppDirectory $WorkDir
nssm set $Name Start SERVICE_AUTO_START
nssm set $Name AppStdout "$WorkDir\logs\service.out.log"
nssm set $Name AppStderr "$WorkDir\logs\service.err.log"
nssm start $Name
Write-Host "Service $Name installed and started."
