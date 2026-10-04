# Starts HR-System for a presentation: an EMPTY installation (so the set-up screen shows) that offers "Development stage: Skip".
# Skip builds the demo company (tools/make_demo.py) and opens it. Every start begins from nothing: the previous presentation folder is removed.
param([switch]$NoBrowser, [int]$Port = 8791, [string]$Folder = '')
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if (-not $Folder) { $Folder = Join-Path (Split-Path -Parent $repo) 'HR-Presentation' }
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { Write-Host 'Python 3.10 or newer is needed (https://www.python.org/downloads/).' -ForegroundColor Red; exit 1 }
if ((Test-Path $Folder) -and -not (Test-Path (Join-Path $Folder '.presentation'))) {
  if (Get-ChildItem $Folder -Force | Select-Object -First 1) { Write-Host "$Folder exists and is not a presentation folder: refusing to touch it." -ForegroundColor Red; exit 1 }
}
if (Test-Path $Folder) { Remove-Item $Folder -Recurse -Force }
Remove-Item "$Folder.demo-build" -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $Folder | Out-Null
Set-Content (Join-Path $Folder '.presentation') 'presentation folder: removed and rebuilt on every start'
$env:PYTHONPATH = Join-Path $repo 'vendor.zip'
$env:OPENBLAS_NUM_THREADS = '1'
$env:HR_HOME = $Folder
$env:HR_DEMO_SKIP = '1'
Set-Location $repo
Write-Host "HR-System PRESENTATION  ->  http://127.0.0.1:$Port/" -ForegroundColor Green
Write-Host '  Set-up screen first. Press "Development stage: Skip" to enter the demo company (about 30 seconds). Then sign in: admin / 123'
Write-Host '  Close this window to stop.'
$serverArgs = @('hr_main.py', '--port', $Port)
if ($NoBrowser) { $serverArgs += '--no-browser' }
& $python @serverArgs
exit $LASTEXITCODE
