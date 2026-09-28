# Starts the HR-System DEMO: a separate installation filled with realistic synthetic data (tools/make_demo.py).
# It never touches a real installation. First run: builds the demo (about 20 seconds). Then: starts it and opens it.
#   Start-HR-Demo.bat            start (build if missing)
#   Start-HR-Demo.bat -Reset     rebuild the demo from scratch, then start
param([switch]$Reset, [int]$Port = 8790, [string]$Folder = '')
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if (-not $Folder) { $Folder = Join-Path (Split-Path -Parent $repo) 'HR-Demo' }
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { Write-Host 'Python 3.10 or newer is needed for the demo (https://www.python.org/downloads/).' -ForegroundColor Red; exit 1 }
$env:PYTHONPATH = Join-Path $repo 'vendor.zip'
$env:OPENBLAS_NUM_THREADS = '1'
Set-Location $repo
if ($Reset -or -not (Test-Path (Join-Path $Folder '.hr-demo'))) {
  Write-Host "Building the demo in $Folder ..." -ForegroundColor Cyan
  $args_ = @('tools/make_demo.py', $Folder)
  if ($Reset) { $args_ += '--reset' }
  & $python @args_
  if ($LASTEXITCODE -ne 0) { Write-Host 'The demo could not be built (see above).' -ForegroundColor Red; exit 1 }
}
$env:HR_HOME = $Folder
Write-Host ''
Write-Host "HR-System DEMO  ->  http://127.0.0.1:$Port/" -ForegroundColor Green
Write-Host '  Sign in: admin / 123     Other users (mona.hassan, karim.adel, omar.farouk ...): Demo-2026!pass'
Write-Host '  Close this window to stop the demo.'
& $python hr_main.py --port $Port
