# Level Bridge STEM - Windows laptop: setup, tests and the full Teach -> Learn -> Improve demo (no model).
# Run from the project folder:
#   powershell -ExecutionPolicy Bypass -File scripts\windows_demo.ps1
# Re-run any time; setup is skipped when .venv already exists.
param([switch]$NoReset, [switch]$NoOpen, [switch]$SkipTests)
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONUTF8 = "1"                  # read/write every file as UTF-8 (÷, ³, → in passages and outputs)
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = "$PWD\src"
$py = ".\.venv\Scripts\python.exe"

function Step($t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan }
function Run([string[]]$a) {
    & $py -m level_bridge.main @a
    if ($LASTEXITCODE -ne 0) { Write-Host "FAILED (exit $LASTEXITCODE): $($a -join ' ')" -ForegroundColor Red; exit 1 }
}

Step "0. Python and virtual environment"
if (-not (Test-Path $py)) {
    python --version
    if ($LASTEXITCODE -ne 0) { Write-Host "Python not found. Install Python 3.11-3.13 from python.org (tick 'Add python.exe to PATH')." -ForegroundColor Red; exit 1 }
    python -m venv .venv
    & $py -m pip install --upgrade pip
    & $py -m pip install -r requirements.txt
}
& $py --version

if (-not $SkipTests) {
Step "1. Automated tests"
& $py -m pytest -q -p no:cacheprovider
if ($LASTEXITCODE -ne 0) { Write-Host "Some tests failed - send the output above." -ForegroundColor Red; exit 1 }
}

Step "2. Reset demo stores"
if (-not $NoReset) {
foreach ($relative in @('data\learners','data\hub','data\packs','usb_export')) {
    $target = [IO.Path]::GetFullPath((Join-Path $PWD $relative))
    $workspacePrefix = [IO.Path]::GetFullPath($PWD.Path).TrimEnd('\') + '\'
    if (-not $target.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe demo reset path' }
    Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
}
}
New-Item -ItemType Directory -Force usb_export | Out-Null

Step "3. TEACH - build and approve lesson packs (template backend: NOT LLM inference on a laptop)"
Run @("pack-build", "--backend", "template", "--passage", "data/passages/speed_passage.txt", "--out", "data/packs/speed.lbpack.json")
Run @("pack-build", "--backend", "template", "--passage", "data/passages/density_passage.txt", "--out", "data/packs/density.lbpack.json")
Run @("pack-review", "--pack", "data/packs/speed.lbpack.json", "--approve-all")
Run @("pack-review", "--pack", "data/packs/density.lbpack.json", "--approve-all")

Step "4. LEARN - model-free sessions (scripted learners, pseudonymous IDs)"
Run @("session", "--pack", "data/packs/speed.lbpack.json", "--answers", "data/test_cases/priya_answers.json", "--learner", "STU-7F3A", "--consent", "--run-id", "demo_priya_speed")
Run @("session", "--pack", "data/packs/density.lbpack.json", "--answers", "data/test_cases/priya_density_answers.json", "--learner", "STU-7F3A", "--run-id", "demo_priya_density")
Run @("session", "--pack", "data/packs/speed.lbpack.json", "--answers", "data/test_cases/strong_reader_answers.json", "--learner", "STU-K2M9", "--consent", "--run-id", "demo_ravi_speed")
Run @("session", "--pack", "data/packs/density.lbpack.json", "--answers", "data/test_cases/ravi_density_answers.json", "--learner", "STU-K2M9", "--run-id", "demo_ravi_density")
Run @("session", "--pack", "data/packs/speed.lbpack.json", "--answers", "data/test_cases/meena_speed_answers.json", "--learner", "STU-M4Q8", "--consent", "--run-id", "demo_meena_speed")

Step "5. IMPROVE - learner memory, USB export, hub import, CBS portal"
Run @("profile-show", "--learner", "STU-7F3A")
foreach ($l in "STU-7F3A", "STU-K2M9", "STU-M4Q8") { Run @("profile-export", "--learner", $l, "--out", "usb_export") }
Run @("hub-import", "--dir", "usb_export")
Run @("portal")

Step "Done - opening the CBS portal"
if (-not $NoOpen) { Start-Process "outputs\cbs_portal.html" }
