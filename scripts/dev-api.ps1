$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ApiDir = Join-Path $Root "apps\api"
$VenvDir = Join-Path $ApiDir ".venv"

Set-Location $ApiDir

if (-not (Test-Path $VenvDir)) {
  python -m venv $VenvDir
}

& (Join-Path $VenvDir "Scripts\Activate.ps1")
python -m pip install --upgrade pip
pip install -r requirements.txt

if (Test-Path (Join-Path $Root ".env")) {
  Get-Content (Join-Path $Root ".env") | ForEach-Object {
    if ($_ -match "^\s*([^#][^=]+)=(.*)$") {
      [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
  }
}

$env:API_HOST = if ($env:API_HOST) { $env:API_HOST } else { "127.0.0.1" }
$env:API_PORT = if ($env:API_PORT) { $env:API_PORT } else { "8000" }

uvicorn app.main:app --host $env:API_HOST --port ([int]$env:API_PORT) --reload
