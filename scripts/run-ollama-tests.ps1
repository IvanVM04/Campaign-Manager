<#
.SYNOPSIS
    Runs local Stanza and real-Ollama evaluations and writes consolidated reports.
.DESCRIPTION
    Safely updates main, prepares only the Python dependencies needed for local
    evaluation, runs the offline NLP benchmark, executes real Ollama tests and
    optionally the guarded Intent-versus-Stanza A/B.
    CI-owned deterministic tests, coverage, lint, typing and JavaScript checks are
    intentionally left to GitHub Actions and are not repeated by this script.
    Each run gets unique logs, JUnit, JSON and Markdown reports under
    artifacts/quality-runs. It never stashes, resets, cleans or overwrites user
    work and never downloads Ollama models. Stanza downloads are explicit.
#>
[CmdletBinding()]
param(
    [string]$EnvFile = ".env.ollama",
    [string]$BaseUrl,
    [string]$Model,
    [string]$IntentModel,
    [string]$ExtractionModel,
    [string]$MechanicsModel,
    [string]$NarrativeModel,
    [string]$TimeoutSeconds,
    [ValidateSet("true", "false")][string]$Think,
    [string]$HardwareLabel,
    [string]$ScenarioId,
    [string]$CompoundScenarioId,
    [string]$V3ShadowScenarioId,
    [ValidateSet("all", "language", "semantic-frames", "discourse", "compound-intent", "v3-shadow")][string]$Evaluation = "all",
    [string]$NlpModelDirectory,
    [string]$ResultsRoot = "artifacts/quality-runs",
    [switch]$RunNlpAb,
    [switch]$SkipOllamaTests,
    [switch]$SkipNlpPilot,
    [switch]$SkipNlpModelDownload,
    [switch]$NoUpdate,
    [switch]$SkipDependencySync,
    [switch]$SkipOllamaPreflight
)

$ErrorActionPreference = "Stop"
$script:Stages = New-Object System.Collections.Generic.List[object]

function Write-Section([string]$Title) {
    Write-Host ""
    Write-Host ("=" * 76) -ForegroundColor DarkCyan
    Write-Host ("  " + $Title) -ForegroundColor Cyan
    Write-Host ("=" * 76) -ForegroundColor DarkCyan
}

function Add-Stage([string]$Name, [string]$Status, [double]$Seconds = 0, [Nullable[int]]$Code = $null, [string]$Log = "", [string]$Details = "") {
    $item = [pscustomobject]@{ name = $Name; status = $Status; duration_seconds = [Math]::Round($Seconds, 2); exit_code = $Code; log = $Log; details = $Details }
    $null = $script:Stages.Add($item)
    $color = switch ($Status) { "success" { "Green" } "failed" { "Red" } "warning" { "Yellow" } default { "DarkGray" } }
    Write-Host ("[{0,-7}] {1,-44} {2,7:N1}s" -f $Status.ToUpperInvariant(), $Name, $Seconds) -ForegroundColor $color
    if ($Details) { Write-Host ("          " + $Details) -ForegroundColor DarkGray }
    return $item
}

function Invoke-Git([string[]]$Arguments) {
    # Git writes normal fetch/pull progress to stderr. Do not let that diagnostic
    # stream become a terminating PowerShell error under the script's Stop policy.
    $savedErrorActionPreference = $ErrorActionPreference
    $gitOutput = @()
    $gitExitCode = 1
    try {
        $ErrorActionPreference = "Continue"
        $gitOutput = @(& git -C $script:RepoRoot @Arguments 2>&1)
        $gitExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $savedErrorActionPreference
    }

    foreach ($line in $gitOutput) {
        if ($line -is [System.Management.Automation.ErrorRecord]) {
            Write-Host $line.ToString()
        }
        else {
            Write-Host ([string]$line)
        }
    }

    if ($gitExitCode -ne 0) {
        throw "git $($Arguments -join ' ') failed with exit code $gitExitCode"
    }
}

function Set-EnvDefault([string]$Name, [AllowEmptyString()][string]$Value) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($Name, "Process"))) {
        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }
}

function Set-EnvOverride([string]$Name, [AllowEmptyString()][string]$Value) {
    if (-not [string]::IsNullOrWhiteSpace($Value)) {
        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }
}

function Import-EnvFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $line = $line.Trim()
        if (-not $line -or $line.StartsWith("#")) { continue }
        if ($line.StartsWith("export ")) { $line = $line.Substring(7).Trim() }
        if ($line -notmatch '^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { Write-Warning "Ignoring unsupported env-file line."; continue }
        $name = $Matches[1]
        $value = $Matches[2].Trim()
        if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        Set-EnvDefault $name $value
    }
}

function Get-Python {
    $candidate = Join-Path $script:RepoRoot ".venv/Scripts/python.exe"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    $candidate = Join-Path $script:RepoRoot ".venv/bin/python"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) { if ($command.Path) { return $command.Path }; return $command.Source }
    return $null
}

function Invoke-CommandStage([string]$Name, [string]$Exe, [string[]]$CommandArgs, [string]$LogName, [string]$Details = "") {
    $path = Join-Path $script:LogDir $LogName
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $code = 1
    try {
        Push-Location $script:RepoRoot
        try {
            $global:LASTEXITCODE = 0
            & $Exe @CommandArgs 2>&1 | Tee-Object -FilePath $path | Out-Host
            $code = $LASTEXITCODE
        }
        finally { Pop-Location }
    }
    catch {
        ($_ | Out-String) | Add-Content -LiteralPath $path -Encoding UTF8
        if (-not $Details) { $Details = "Command failed to start or complete; inspect the log." }
    }
    $watch.Stop()
    $status = if ($code -eq 0) { "success" } else { "failed" }
    return Add-Stage $Name $status $watch.Elapsed.TotalSeconds $code ("logs/" + $LogName) $Details
}

function Test-StanzaModels([string]$ModelDir) {
    if (-not (Test-Path -LiteralPath (Join-Path $ModelDir "resources.json") -PathType Leaf)) { return $false }
    foreach ($processor in @("tokenize", "mwt", "pos", "lemma", "depparse")) {
        $folder = Join-Path (Join-Path $ModelDir "es") $processor
        if (-not (Test-Path -LiteralPath $folder -PathType Container)) { return $false }
        $file = Get-ChildItem -LiteralPath $folder -Filter "*.pt" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $file) { return $false }
    }
    return $true
}

function Invoke-OllamaPreflight([string]$Url, [string[]]$RequiredModels) {
    $watch = [Diagnostics.Stopwatch]::StartNew()
    try {
        $version = Invoke-RestMethod -Method Get -Uri ($Url.TrimEnd("/") + "/api/version") -TimeoutSec 10
        $tags = Invoke-RestMethod -Method Get -Uri ($Url.TrimEnd("/") + "/api/tags") -TimeoutSec 20
        $installed = @()
        if ($tags.models) { $installed = @($tags.models | ForEach-Object { if ($_.name) { [string]$_.name } elseif ($_.model) { [string]$_.model } }) }
        $missing = @()
        foreach ($required in ($RequiredModels | Where-Object { $_ } | Sort-Object -Unique)) {
            if ($installed -notcontains $required -and $installed -notcontains ($required + ":latest")) { $missing += $required }
        }
        if ($missing.Count) { throw ("Missing Ollama models: " + ($missing -join ", ")) }
        Write-Host ("Ollama {0}; all configured models available." -f $version.version)
        $watch.Stop()
        Add-Stage "Ollama service/model preflight" "success" $watch.Elapsed.TotalSeconds 0 "" "Endpoint reachable; required models found." | Out-Null
        return $true
    }
    catch {
        $watch.Stop()
        Write-Warning ("Ollama preflight failed: " + $_.Exception.Message)
        Add-Stage "Ollama service/model preflight" "failed" $watch.Elapsed.TotalSeconds 1 "" "Endpoint or model unavailable. No Ollama model is downloaded automatically." | Out-Null
        return $false
    }
}

function Write-Manifest([string]$Path, [string]$Commit, [datetime]$Start, [datetime]$Finish) {
    $payload = [ordered]@{
        schema_version = 1
        commit = $Commit
        started_at = $Start.ToString("o")
        finished_at = $Finish.ToString("o")
        duration_seconds = [Math]::Round(($Finish - $Start).TotalSeconds, 2)
        stages = @($script:Stages.ToArray())
    }
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, (($payload | ConvertTo-Json -Depth 12) + [Environment]::NewLine), $encoding)
}

if ($RunNlpAb -and $SkipNlpPilot) { throw "-RunNlpAb requires the NLP pilot; remove -SkipNlpPilot." }

# Resolve repository and refuse to switch branches with any tracked/untracked work.
$rootOutput = & git -C (Join-Path $PSScriptRoot "..") rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($rootOutput -join ""))) { throw "No Git repository found from script location." }
$script:RepoRoot = (Resolve-Path -LiteralPath ($rootOutput -join "")).Path
$dirty = & git -C $script:RepoRoot status --porcelain
if ($LASTEXITCODE -ne 0) { throw "Could not inspect Git working tree." }
if ($dirty) { throw "Working tree is not clean. Commit/save local changes first; no files or branches were changed." }

Write-Section "1/5  Repository and configuration"
if (-not $NoUpdate) {
    Invoke-Git @("fetch", "origin", "main")
    & git -C $script:RepoRoot show-ref --verify --quiet refs/heads/main
    if ($LASTEXITCODE -eq 0) { Invoke-Git @("switch", "main") } else { Invoke-Git @("switch", "--track", "-c", "main", "origin/main") }
    Invoke-Git @("pull", "--ff-only", "origin", "main")
}
else {
    $current = (& git -C $script:RepoRoot branch --show-current).Trim()
    if ($current -ne "main") { throw "-NoUpdate requires the current branch to be main." }
}
$commit = (& git -C $script:RepoRoot rev-parse HEAD).Trim()
Write-Host ("Branch main | commit " + $commit) -ForegroundColor Green

if ($EnvFile) {
    $envPath = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $script:RepoRoot $EnvFile }
    if (Test-Path -LiteralPath $envPath -PathType Leaf) { Import-EnvFile $envPath; Write-Host "Loaded local env file; existing shell values take precedence." }
    else { Write-Host "No .env.ollama file; shell variables and defaults will be used." }
}

Set-EnvOverride "CAMPAIGN_MANAGER_REAL_LLM_BASE_URL" $BaseUrl
Set-EnvOverride "CAMPAIGN_MANAGER_OLLAMA_BASE_URL" $BaseUrl
Set-EnvOverride "CAMPAIGN_MANAGER_REAL_LLM_MODEL" $Model
Set-EnvOverride "CAMPAIGN_MANAGER_LLM_INTENT_MODEL" $IntentModel
Set-EnvOverride "CAMPAIGN_MANAGER_LLM_EXTRACTION_MODEL" $ExtractionModel
Set-EnvOverride "CAMPAIGN_MANAGER_LLM_MECHANICS_MODEL" $MechanicsModel
Set-EnvOverride "CAMPAIGN_MANAGER_LLM_NARRATIVE_MODEL" $NarrativeModel
Set-EnvOverride "CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT" $TimeoutSeconds
Set-EnvOverride "CAMPAIGN_MANAGER_REAL_LLM_HARDWARE" $HardwareLabel
if ($Think) { Set-EnvOverride "CAMPAIGN_MANAGER_REAL_LLM_THINK" $Think; Set-EnvOverride "CAMPAIGN_MANAGER_OLLAMA_THINK" $Think }

if ($Model) {
    $roleOverrides = @{ INTENT = $IntentModel; EXTRACTION = $ExtractionModel; MECHANICS = $MechanicsModel; NARRATIVE = $NarrativeModel }
    foreach ($role in @("INTENT", "MECHANICS", "EXTRACTION", "NARRATIVE")) {
        if ([string]::IsNullOrWhiteSpace($roleOverrides[$role])) { Set-EnvOverride "CAMPAIGN_MANAGER_LLM_$($role)_MODEL" $Model }
    }
}
if ($TimeoutSeconds) {
    foreach ($role in @("INTENT", "MECHANICS", "EXTRACTION", "NARRATIVE")) { Set-EnvOverride "CAMPAIGN_MANAGER_LLM_$($role)_TIMEOUT_SECONDS" $TimeoutSeconds }
}
if ($Think) {
    foreach ($role in @("INTENT", "MECHANICS", "EXTRACTION", "NARRATIVE")) { Set-EnvOverride "CAMPAIGN_MANAGER_LLM_$($role)_THINK" $Think }
}
if ([string]::IsNullOrWhiteSpace($env:CAMPAIGN_MANAGER_REAL_LLM_BASE_URL)) { Set-EnvDefault "CAMPAIGN_MANAGER_REAL_LLM_BASE_URL" $env:CAMPAIGN_MANAGER_OLLAMA_BASE_URL }
if ([string]::IsNullOrWhiteSpace($env:CAMPAIGN_MANAGER_OLLAMA_BASE_URL)) { Set-EnvDefault "CAMPAIGN_MANAGER_OLLAMA_BASE_URL" $env:CAMPAIGN_MANAGER_REAL_LLM_BASE_URL }
Set-EnvDefault "CAMPAIGN_MANAGER_OLLAMA_BASE_URL" "http://localhost:11434"
Set-EnvDefault "CAMPAIGN_MANAGER_REAL_LLM_BASE_URL" $env:CAMPAIGN_MANAGER_OLLAMA_BASE_URL
Set-EnvDefault "CAMPAIGN_MANAGER_REAL_LLM_MODEL" "gemma4:12b-it-q4_K_M"
Set-EnvDefault "CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT" "300"
Set-EnvDefault "CAMPAIGN_MANAGER_OLLAMA_THINK" "false"
Set-EnvDefault "CAMPAIGN_MANAGER_REAL_LLM_THINK" $env:CAMPAIGN_MANAGER_OLLAMA_THINK
Set-EnvOverride "CAMPAIGN_MANAGER_GIT_COMMIT" $commit
foreach ($role in @("INTENT", "MECHANICS", "EXTRACTION", "NARRATIVE")) {
    Set-EnvDefault "CAMPAIGN_MANAGER_LLM_$($role)_MODEL" $env:CAMPAIGN_MANAGER_REAL_LLM_MODEL
    Set-EnvDefault "CAMPAIGN_MANAGER_LLM_$($role)_TIMEOUT_SECONDS" $env:CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT
}

if ([string]::IsNullOrWhiteSpace($NlpModelDirectory)) {
    if ($env:CAMPAIGN_MANAGER_NLP_PILOT_MODEL_DIR) { $NlpModelDirectory = $env:CAMPAIGN_MANAGER_NLP_PILOT_MODEL_DIR }
    else { $NlpModelDirectory = Join-Path $HOME "stanza_resources" }
}
$NlpModelDirectory = [IO.Path]::GetFullPath($NlpModelDirectory)
Set-EnvOverride "CAMPAIGN_MANAGER_NLP_PILOT_MODEL_DIR" $NlpModelDirectory
Remove-Item Env:CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID -ErrorAction SilentlyContinue
Remove-Item Env:CAMPAIGN_MANAGER_REAL_LLM_COMPOUND_SCENARIO_ID -ErrorAction SilentlyContinue
Remove-Item Env:CAMPAIGN_MANAGER_REAL_LLM_V3_SHADOW_SCENARIO_ID -ErrorAction SilentlyContinue
if ($ScenarioId) {
    if ($Evaluation -notin @("language", "semantic-frames", "discourse")) { throw "-ScenarioId requires language, semantic-frames or discourse." }
    Set-EnvOverride "CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID" $ScenarioId
}
if ($CompoundScenarioId) {
    if ($Evaluation -ne "compound-intent") { throw "-CompoundScenarioId requires compound-intent." }
    Set-EnvOverride "CAMPAIGN_MANAGER_REAL_LLM_COMPOUND_SCENARIO_ID" $CompoundScenarioId
}
if ($V3ShadowScenarioId) {
    if ($Evaluation -ne "v3-shadow") { throw "-V3ShadowScenarioId requires v3-shadow." }
    Set-EnvOverride "CAMPAIGN_MANAGER_REAL_LLM_V3_SHADOW_SCENARIO_ID" $V3ShadowScenarioId
}

$startedAt = Get-Date
$tag = $startedAt.ToString("yyyyMMdd-HHmmss") + "-" + $commit.Substring(0, 8)
$resultsRootPath = Join-Path $script:RepoRoot $ResultsRoot
New-Item -ItemType Directory -Force -Path $resultsRootPath | Out-Null
$script:RunDir = Join-Path $resultsRootPath $tag
$counter = 1
while (Test-Path -LiteralPath $script:RunDir) { $script:RunDir = Join-Path $resultsRootPath ($tag + "-" + $counter); $counter++ }
$script:LogDir = Join-Path $script:RunDir "logs"
$ollamaDir = Join-Path $script:RunDir "ollama"
$reportDir = Join-Path $ollamaDir "reports"
$nlpDir = Join-Path $script:RunDir "nlp"
New-Item -ItemType Directory -Force -Path $script:LogDir, $reportDir, $nlpDir | Out-Null
Write-Host ("Results: " + $script:RunDir) -ForegroundColor Cyan

Write-Section "2/5  Python environment"
if ($SkipDependencySync) {
    Add-Stage "Dependency synchronization" "skipped" 0 $null "" "Using existing environment by request." | Out-Null
}
else {
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) {
        $uvExe = if ($uv.Path) { $uv.Path } else { $uv.Source }
        Invoke-CommandStage "Sync Python groups (test/nlp-pilot)" $uvExe @("sync", "--no-install-project", "--group", "test", "--group", "nlp-pilot", "--no-lock") "00-dependencies.log" | Out-Null
    }
    else {
        $systemPython = Get-Command python -ErrorAction SilentlyContinue
        if (-not $systemPython) { Add-Stage "Dependency synchronization" "failed" 0 1 "" "Install Python 3.12+ or uv."; }
        else {
            $sysExe = if ($systemPython.Path) { $systemPython.Path } else { $systemPython.Source }
            if (-not (Get-Python)) { Invoke-CommandStage "Create private Python virtualenv" $sysExe @("-m", "venv", ".venv") "00-venv.log" | Out-Null }
            $venvPython = Get-Python
            if ($venvPython) {
                Invoke-CommandStage "Upgrade pip" $venvPython @("-m", "pip", "install", "--upgrade", "pip") "00-pip.log" | Out-Null
                # The repository is executed from its root; it is not an editable
                # installable Python package. Match CI/AGENTS.md: install runtime
                # requirements and PEP 735 development groups separately.
                Invoke-CommandStage "Install application requirements" $venvPython @("-m", "pip", "install", "-r", "requirements.txt") "00-requirements.log" | Out-Null
                Invoke-CommandStage "Install test/nlp-pilot groups" $venvPython @("-m", "pip", "install", "--group", "test", "--group", "nlp-pilot") "00-groups.log" | Out-Null
            }
        }
    }
}

$python = Get-Python
if ($python) { Invoke-CommandStage "Python 3.12+ preflight" $python @("-c", "import sys; print(sys.version.split()[0]); raise SystemExit(0 if sys.version_info >= (3, 12) else 1)") "00-python-version.log" | Out-Null }
else { Add-Stage "Python interpreter preflight" "failed" 0 1 "" "No Python interpreter found." | Out-Null }
Write-Section "3/5  Stanza offline pilot"
$offlineReport = Join-Path $nlpDir "offline.json"
$stanzaReady = $false
if ($SkipNlpPilot) {
    Add-Stage "Stanza model preparation" "skipped" 0 $null "" "SkipNlpPilot." | Out-Null
    Add-Stage "Offline NLP benchmark" "skipped" 0 $null "" "SkipNlpPilot." | Out-Null
}
elseif (-not $python) {
    Add-Stage "Stanza model preparation" "failed" 0 1 "" "Python unavailable." | Out-Null
    Add-Stage "Offline NLP benchmark" "skipped" 0 $null "" "Python unavailable." | Out-Null
}
elseif (Test-StanzaModels $NlpModelDirectory) {
    $stanzaReady = $true
    Add-Stage "Stanza model preparation" "success" 0 0 "" "Spanish processors already installed; no download needed." | Out-Null
}
elseif ($SkipNlpModelDownload) {
    Add-Stage "Stanza model preparation" "failed" 0 1 "" "Model missing and SkipNlpModelDownload was supplied." | Out-Null
}
else {
    New-Item -ItemType Directory -Force -Path $NlpModelDirectory | Out-Null
    $download = Invoke-CommandStage "Download Stanza Spanish processors" $python @("-m", "scripts.download_nlp_pilot_models", "--model-dir", $NlpModelDirectory) "20-stanza-download.log" "Explicit download of tokenize/mwt/pos/lemma/depparse."
    $stanzaReady = ($download.Status -eq "success") -and (Test-StanzaModels $NlpModelDirectory)
    if ($download.Status -eq "success" -and -not $stanzaReady) { $download.Status = "failed"; $download.ExitCode = 1; $download.details = "Download completed but one or more processor model files are missing." }
}
if ($stanzaReady) {
    Invoke-CommandStage "Offline NLP benchmark (development + held-out)" $python @("-m", "scripts.run_nlp_pilot", "--split", "both", "--model-dir", $NlpModelDirectory, "--output", $offlineReport) "21-nlp-offline.log" | Out-Null
}
elseif (-not $SkipNlpPilot) {
    Add-Stage "Offline NLP benchmark" "skipped" 0 $null "" "Stanza models are not available." | Out-Null
}

Write-Section "4/5  Ollama real tests and A/B"
$runOllama = (-not $SkipOllamaTests) -or $RunNlpAb
$ollamaReady = $true
$base = $env:CAMPAIGN_MANAGER_REAL_LLM_BASE_URL.TrimEnd("/")
$models = @($env:CAMPAIGN_MANAGER_REAL_LLM_MODEL)
foreach ($name in @("CAMPAIGN_MANAGER_LLM_INTENT_MODEL", "CAMPAIGN_MANAGER_LLM_EXTRACTION_MODEL", "CAMPAIGN_MANAGER_LLM_MECHANICS_MODEL", "CAMPAIGN_MANAGER_LLM_NARRATIVE_MODEL")) {
    $value = [Environment]::GetEnvironmentVariable($name, "Process")
    if ($value) { $models += $value }
}
if ($runOllama -and -not $SkipOllamaPreflight) { $ollamaReady = Invoke-OllamaPreflight $base $models }
elseif (-not $runOllama) { Add-Stage "Ollama preflight" "skipped" 0 $null "" "Ollama tests not requested." | Out-Null }
else { Add-Stage "Ollama preflight" "skipped" 0 $null "" "SkipOllamaPreflight explicitly supplied." | Out-Null }

$ollamaDir = Join-Path $script:RunDir "ollama"
$reportDir = Join-Path $ollamaDir "reports"
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
Set-EnvOverride "CAMPAIGN_MANAGER_REAL_LLM_REPORT_DIR" $reportDir
Set-EnvOverride "CAMPAIGN_MANAGER_REAL_LLM_REPORT_PATH" (Join-Path $reportDir "semantic-holdout.json")
Set-EnvOverride "CAMPAIGN_MANAGER_REAL_LLM_COMPOUND_REPORT_PATH" (Join-Path $reportDir "compound-intent.json")
# The v3 shadow test writes a separate, privacy-safe report. Always scope it to
# this run so reports from prior runs cannot be mistaken for current evidence.
[Environment]::SetEnvironmentVariable("CAMPAIGN_MANAGER_REAL_LLM_V3_SHADOW_REPORT_PATH", (Join-Path $reportDir "player-turn-v3-shadow.json"), "Process")
$ollamaJUnit = Join-Path $script:LogDir "ollama.junit.xml"
$abJUnit = Join-Path $script:LogDir "nlp-ab.junit.xml"
$abReport = Join-Path $reportDir "nlp-pilot-ab.json"

if ($SkipOllamaTests) { Add-Stage "Ollama real_llm tests" "skipped" 0 $null "" "SkipOllamaTests." | Out-Null }
elseif (-not $ollamaReady) { Add-Stage "Ollama real_llm tests" "skipped" 0 $null "" "Ollama preflight failed." | Out-Null }
elseif ($python) {
    $ollamaPytestArgs = @("-m", "pytest", "-m", "real_llm and not nlp_pilot", "-v", "--durations=25", "--junitxml", $ollamaJUnit)
    $keywords = @{
        "language" = "held_out_language_understanding_corpus_v1"
        "semantic-frames" = "held_out_semantic_frame_corpus_v1"
        "discourse" = "held_out_discourse_intent_and_resolution_corpus"
        "compound-intent" = "compound_intent_understanding_holdout"
        "v3-shadow" = "player_turn_v3_shadow_holdout"
    }
    if ($Evaluation -ne "all") { $ollamaPytestArgs += @("-k", $keywords[$Evaluation]) }
    Invoke-CommandStage "Ollama real_llm test suite" $python $ollamaPytestArgs "30-ollama.log" | Out-Null
}
else { Add-Stage "Ollama real_llm tests" "failed" 0 1 "" "Python unavailable." | Out-Null }

if ($RunNlpAb -and $ollamaReady -and $stanzaReady -and $python) {
    $names = @("CAMPAIGN_MANAGER_NLP_PILOT_LIVE", "CAMPAIGN_MANAGER_NLP_PILOT_MODEL_DIR", "CAMPAIGN_MANAGER_NLP_PILOT_REPORT_PATH")
    $previous = @{}
    foreach ($name in $names) { $previous[$name] = [Environment]::GetEnvironmentVariable($name, "Process") }
    try {
        [Environment]::SetEnvironmentVariable("CAMPAIGN_MANAGER_NLP_PILOT_LIVE", "1", "Process")
        [Environment]::SetEnvironmentVariable("CAMPAIGN_MANAGER_NLP_PILOT_MODEL_DIR", $NlpModelDirectory, "Process")
        [Environment]::SetEnvironmentVariable("CAMPAIGN_MANAGER_NLP_PILOT_REPORT_PATH", $abReport, "Process")
        Invoke-CommandStage "Intent vs. Stanza live A/B" $python @("-m", "pytest", "tests/test_real_llm_nlp_pilot.py", "-m", "real_llm and nlp_pilot", "-v", "--durations=25", "--junitxml", $abJUnit) "31-nlp-ab.log" "Extra Ollama calls; both variants use the same model/configuration/gold." | Out-Null
    }
    finally { foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $previous[$name], "Process") } }
}
elseif ($RunNlpAb) {
    Add-Stage "Intent vs. Stanza live A/B" "skipped" 0 $null "" "Requires Ollama, Stanza models and Python to be ready." | Out-Null
}
else {
    Add-Stage "Intent vs. Stanza live A/B" "skipped" 0 $null "" "Optional extra calls; pass -RunNlpAb to enable." | Out-Null
}

if ((-not $SkipOllamaTests) -and $python) {
    Invoke-CommandStage "Ollama aggregate report" $python @("scripts/ollama_test_report.py", "--junit-xml", $ollamaJUnit, "--output-dir", $ollamaDir, "--commit", $commit) "32-ollama-report.log" | Out-Null
}
else { Add-Stage "Ollama aggregate report" "skipped" 0 $null "" "Main Ollama suite not run." | Out-Null }

Write-Section "5/5  Consolidated report"
$manifest = Join-Path $script:RunDir "run-manifest.json"
$finished = Get-Date
Write-Manifest $manifest $commit $startedAt $finished
if (-not $python) {
    Add-Stage "Consolidated report" "failed" 0 1 "" "Python unavailable to generate the final report." | Out-Null
    Write-Manifest $manifest $commit $startedAt (Get-Date)
    exit 1
}
$reportScript = Join-Path $script:RepoRoot "scripts/quality_run_report.py"
$reportArgs = @($reportScript, "--run-dir", $script:RunDir, "--manifest", $manifest, "--commit", $commit)
if (Test-Path -LiteralPath $ollamaJUnit) { $reportArgs += @("--ollama-junit", $ollamaJUnit) }
$ollamaSummary = Join-Path $ollamaDir "summary.json"
if (Test-Path -LiteralPath $ollamaSummary) { $reportArgs += @("--ollama-summary", $ollamaSummary) }
if (Test-Path -LiteralPath $offlineReport) { $reportArgs += @("--nlp-offline", $offlineReport) }
if (Test-Path -LiteralPath $abJUnit) { $reportArgs += @("--nlp-ab-junit", $abJUnit) }
if (Test-Path -LiteralPath $abReport) { $reportArgs += @("--nlp-ab-report", $abReport) }
$reportStage = Invoke-CommandStage "Generate consolidated Markdown + JSON report" $python $reportArgs "99-report.log"
$finished = Get-Date
Write-Manifest $manifest $commit $startedAt $finished
$null = & $python @reportArgs 2>&1 | Tee-Object -FilePath (Join-Path $script:LogDir "99-report-final.log") | Out-Host
$reportExit = $LASTEXITCODE
$failedCount = @($script:Stages | Where-Object { $_.status -eq "failed" }).Count
$chatSummaryPath = Join-Path $script:RunDir "chat-summary.txt"

Write-Host ""
Write-Host "RESUMEN PARA COPIAR Y PEGAR" -ForegroundColor Cyan
Write-Host ("-" * 76) -ForegroundColor DarkCyan
if (Test-Path -LiteralPath $chatSummaryPath -PathType Leaf) {
    Get-Content -LiteralPath $chatSummaryPath -Encoding UTF8 | ForEach-Object { Write-Host $_ }
}
else {
    Write-Host "No se pudo generar chat-summary.txt. Conserva el summary.md y los logs de esta ejecución." -ForegroundColor Yellow
}
Write-Host ("-" * 76) -ForegroundColor DarkCyan

Write-Host ""
Write-Host ("-" * 76) -ForegroundColor DarkCyan
if ($failedCount -eq 0 -and $reportExit -eq 0) { Write-Host "ALL REQUESTED CHECKS PASSED" -ForegroundColor Green }
else { Write-Host ("RUN FINISHED WITH {0} FAILED STAGE(S)" -f $failedCount) -ForegroundColor Red }
Write-Host ("Markdown report: " + (Join-Path $script:RunDir "summary.md")) -ForegroundColor Cyan
Write-Host ("JSON report:     " + (Join-Path $script:RunDir "summary.json")) -ForegroundColor Cyan
Write-Host ("Copy/paste:      " + $chatSummaryPath) -ForegroundColor Cyan
Write-Host ("Logs:            " + $script:LogDir) -ForegroundColor Cyan
Write-Host ("-" * 76) -ForegroundColor DarkCyan
if ($failedCount -gt 0 -or $reportExit -ne 0) { exit 1 }
exit 0
