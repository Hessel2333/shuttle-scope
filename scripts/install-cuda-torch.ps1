param(
  [string]$PyPiIndex = "https://pypi.org/simple",
  [string]$TorchIndex = "https://download.pytorch.org/whl/cu128"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ApiDir = Join-Path $Root "apps\api"
$VenvPython = Join-Path $ApiDir ".venv\Scripts\python.exe"
$VenvPip = Join-Path $ApiDir ".venv\Scripts\pip.exe"

Set-Location $ApiDir

if (-not (Test-Path $VenvPython)) {
  python -m venv (Join-Path $ApiDir ".venv")
}

& $VenvPython -m pip install --upgrade pip -i $PyPiIndex
& $VenvPip install -r requirements.txt -i $PyPiIndex
& $VenvPip install --force-reinstall torch==2.11.0+cu128 torchvision==0.26.0+cu128 --index-url $TorchIndex

@'
import torch
print("torch:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
print("cuda runtime:", torch.version.cuda)
if torch.cuda.is_available():
    print("device:", torch.cuda.get_device_name(0))
'@ | & $VenvPython -
