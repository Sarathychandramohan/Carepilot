# run_queue.ps1
# Pillar C Sequential Evaluation Queue
# IMPORTANT: DO NOT START UNTIL EXPLICIT USER INSTRUCTION

$ErrorActionPreference = "Continue"
$PYTHON = ".\.venv\Scripts\python.exe"
$LOG_FILE = "data\reports\run_queue.log"

# Ensure reports directory exists
New-Item -ItemType Directory -Force -Path "data\reports" | Out-Null

function Log-Message {
    param([string]$msg)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $msg"
    Write-Host $line
    Add-Content -Path $LOG_FILE -Value $line
}

Log-Message "=== STARTING PILLAR C EVALUATION QUEUE ==="

# ---------------------------------------------------------------------------
# Q1: Pilot (60 queries) x {full, no_ehr}
# ---------------------------------------------------------------------------
Log-Message ">>> [Q1.1] Running Pilot (split=gold-synthetic, config=full, subset=60)"
& $PYTHON -m backend.eval.run --config full --split gold-synthetic --seed 42 --subset 60 *>> $LOG_FILE
Log-Message ">>> [Q1.1] Finished Pilot full"

Log-Message ">>> [Q1.2] Running Pilot (split=gold-synthetic, config=no_ehr, subset=60)"
& $PYTHON -m backend.eval.run --config no_ehr --split gold-synthetic --seed 42 --subset 60 *>> $LOG_FILE
Log-Message ">>> [Q1.2] Finished Pilot no_ehr"

# ---------------------------------------------------------------------------
# Q2: NoEHR45 x {full, no_ehr}
# ---------------------------------------------------------------------------
$noehr_path = "data\annotation\queries_noehr_45.jsonl"
if (Test-Path $noehr_path) {
    Log-Message ">>> [Q2.1] Running NoEHR45 (config=full, queries_file=$noehr_path)"
    & $PYTHON -m backend.eval.run --config full --split gold-synthetic --seed 42 --queries-file $noehr_path *>> $LOG_FILE
    Log-Message ">>> [Q2.1] Finished NoEHR45 full"

    Log-Message ">>> [Q2.2] Running NoEHR45 (config=no_ehr, queries_file=$noehr_path)"
    & $PYTHON -m backend.eval.run --config no_ehr --split gold-synthetic --seed 42 --queries-file $noehr_path *>> $LOG_FILE
    Log-Message ">>> [Q2.2] Finished NoEHR45 no_ehr"
} else {
    Log-Message ">>> [Q2] SKIPPED: $noehr_path not found on disk (pending user upload/generation)"
}

# ---------------------------------------------------------------------------
# Q3: Silver-Test Family-Stratified (--per-family 10, 8 families = 80 queries) x {full, no_ehr}
# ---------------------------------------------------------------------------
Log-Message ">>> [Q3.1] Running Silver-Test Stratified (config=full, per-family=10)"
& $PYTHON -m backend.eval.run --config full --split silver-test --seed 42 --subset-strategy family-stratified --per-family 10 *>> $LOG_FILE
Log-Message ">>> [Q3.1] Finished Silver-Test full"

Log-Message ">>> [Q3.2] Running Silver-Test Stratified (config=no_ehr, per-family=10)"
& $PYTHON -m backend.eval.run --config no_ehr --split silver-test --seed 42 --subset-strategy family-stratified --per-family 10 *>> $LOG_FILE
Log-Message ">>> [Q3.2] Finished Silver-Test no_ehr"

Log-Message "=== PILLAR C EVALUATION QUEUE COMPLETE ==="
