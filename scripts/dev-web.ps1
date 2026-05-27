$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$WebDir = Join-Path $Root "apps\web"

Set-Location $WebDir

if (Test-Path (Join-Path $Root ".env")) {
  Get-Content (Join-Path $Root ".env") | ForEach-Object {
    if ($_ -match "^\s*([^#][^=]+)=(.*)$") {
      [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
  }
}

$env:PORT = if ($env:WEB_PORT) { $env:WEB_PORT } else { "3000" }

npm install
npx next dev -p $env:PORT
