$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$ApiDir = Join-Path $Root "apps\api"
$VenvDir = Join-Path $ApiDir ".venv"
$ThirdPartyDir = Join-Path $Root "third_party"
$TrackNetDir = Join-Path $ThirdPartyDir "TrackNetV3"
$ModelDir = Join-Path $Root "data\models\tracknetv3"
$ZipPath = Join-Path $ModelDir "TrackNetV3_ckpts.zip"

if (-not (Test-Path $VenvDir)) {
  python -m venv $VenvDir
}

& (Join-Path $VenvDir "Scripts\Activate.ps1")
python -m pip install --upgrade pip
pip install gdown pandas Pillow tqdm parse pycocotools

New-Item -ItemType Directory -Force -Path $ThirdPartyDir | Out-Null
New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null

if (-not (Test-Path $TrackNetDir)) {
  git clone https://github.com/qaz812345/TrackNetV3.git $TrackNetDir
} else {
  git -C $TrackNetDir pull --ff-only
}

if (-not (Test-Path $ZipPath)) {
  python -m gdown 1CfzE87a0f6LhBp0kniSl1-89zaLCZ8cA -O $ZipPath
}

if (-not (Test-Path $ZipPath)) {
  throw "Checkpoint download failed. Manually download https://drive.google.com/file/d/1CfzE87a0f6LhBp0kniSl1-89zaLCZ8cA/view and place it at: $ZipPath"
}

Expand-Archive -Path $ZipPath -DestinationPath $ModelDir -Force

$CkptDir = Join-Path $ModelDir "ckpts"
$TrackNetFile = Join-Path $CkptDir "TrackNet_best.pt"
$InpaintFile = Join-Path $CkptDir "InpaintNet_best.pt"

if (-not (Test-Path $TrackNetFile)) {
  $FoundTrackNet = Get-ChildItem -Path $ModelDir -Recurse -Filter "TrackNet_best.pt" | Select-Object -First 1
  $FoundInpaint = Get-ChildItem -Path $ModelDir -Recurse -Filter "InpaintNet_best.pt" | Select-Object -First 1
  if (-not $FoundTrackNet) {
    throw "TrackNet checkpoint not found after extraction under: $ModelDir"
  }
  New-Item -ItemType Directory -Force -Path $CkptDir | Out-Null
  Copy-Item -LiteralPath $FoundTrackNet.FullName -Destination $TrackNetFile -Force
  if ($FoundInpaint) {
    Copy-Item -LiteralPath $FoundInpaint.FullName -Destination $InpaintFile -Force
  }
}

Write-Host "TrackNetV3 ready:"
Write-Host "  Repo: $TrackNetDir"
Write-Host "  TrackNet: $TrackNetFile"
Write-Host "  InpaintNet: $InpaintFile"
