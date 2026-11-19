<#
.SYNOPSIS
    Updates main, prepares the local Python environment and runs the real Ollama tests.

.DESCRIPTION
    Refuses to switch branches when the working tree is dirty. It never stashes,
    overwrites local files, downloads Ollama models, or writes prompts/completions
    to the generated reports. An optional .env.ollama file may hold local settings.
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
    [ValidateSet("true", "false")]
    [string]$Think,
    [string]$HardwareLabel,
    [string]$ScenarioId,
    [string]$CompoundScenarioId,
    [string]$ResultsRoot = "artifacts/ollama",
    [switch]$NoUpdate,
    [switch]$SkipDependencySync,
    [switch]$SkipOllamaPreflight
)

$ErrorActionPreference = "Stop"

function Invoke-Git {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    & git -C $script:RepoRoot @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

function Set-ProcessEnvDefault {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )
    $existing = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($existing)) {
        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }
}

function Set-ProcessEnvOverride {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [AllowEmptyString()][string]$Value
    )
    if (-not [string]::IsNullOrWhiteSpace($Value)) {
        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }
}

function Import-SimpleEnvFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }

    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        if ($trimmed.StartsWith("export ")) {
            $trimmed = $trimmed.Substring(7).Trim()
        }
        if ($trimmed -notmatch '^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            Write-Warning "Ignoring an unsupported line in $Path."
            continue
        }

        $name = $Matches[1]
        $value = $Matches[2].Trim()
        if ($value.Length -ge 2) {
            $first = $value.Substring(0, 1)
            $last = $value.Substring($value.Length - 1, 1)
            if (($first -eq '"' -and $last -eq '"') -or
                ($first -eq "'" -and $last -eq "'")) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }

        # A value already present in the shell wins over the local env file.
        Set-ProcessEnvDefault -Name $name -Value $value
    }
}

function Get-VenvPython {
    $windowsPython = Join-Path $script:RepoRoot ".venv/Scripts/python.exe"
    $unixPython = Join-Path $script:RepoRoot ".venv/bin/python"
    if (Test-Path -LiteralPath $windowsPython) {
        return $windowsPython
    }
    if (Test-Path -LiteralPath $unixPython) {
        return $unixPython
    }
    return $null
}

function Invoke-OllamaPreflight {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string[]]$RequiredModels
    )

    try {
        $version = Invoke-RestMethod -Method Get -Uri "$Url/api/version" -TimeoutSec 10
        $tags = Invoke-RestMethod -Method Get -Uri "$Url/api/tags" -TimeoutSec 20
    }
    catch {
        throw "No se pudo consultar Ollama en $Url. Comprueba que Ollama está iniciado y que la URL es correcta. Detalle: $($_.Exception.Message)"
    }

    $installed = @()
    if ($null -ne $tags.models) {
        $installed = @($tags.models | ForEach-Object {
            if ($_.name) { [string]$_.name }
            elseif ($_.model) { [string]$_.model }
        })
    }

    $missing = @()
    foreach ($required in ($RequiredModels | Where-Object { $_ } | Sort-Object -Unique)) {
        $found = $false
        foreach ($modelName in $installed) {
            if ($modelName -eq $required -or $modelName -eq ($required + ":latest")) {
                $found = $true
                break
            }
        }
        if (-not $found) {
            $missing += $required
        }
    }

    Write-Host "Ollama version: $($version.version)"
    if ($missing.Count -gt 0) {
        $modelList = $missing -join ", "
        throw "Faltan modelos en Ollama: $modelList. Instálalos manualmente con 'ollama pull <modelo>' y vuelve a ejecutar el script. No se descarga ningún modelo automáticamente."
    }
    Write-Host "Modelos requeridos disponibles: $($RequiredModels.Count)"
}

# Resolve the repository root from the script's location.
$script:RepoRoot = (& git -C (Join-Path $PSScriptRoot "..") rev-parse --show-toplevel 2>$null)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($script:RepoRoot)) {
    throw "No se ha encontrado un repositorio Git válido desde $PSScriptRoot."
}
$script:RepoRoot = (Resolve-Path -LiteralPath $script:RepoRoot).Path

# Never discard, stash or switch away from uncommitted user work.
$dirty = & git -C $script:RepoRoot status --porcelain
if ($LASTEXITCODE -ne 0) {
    throw "No se pudo comprobar el estado de Git."
}
if ($dirty) {
    throw "El árbol de trabajo no está limpio. Guarda o confirma tus cambios antes de ejecutar este script; no se modificó ninguna rama ni archivo."
}

if (-not $NoUpdate) {
    Invoke-Git -Arguments @("fetch", "origin", "main")
    & git -C $script:RepoRoot show-ref --verify --quiet refs/heads/main
    $hasLocalMain = ($LASTEXITCODE -eq 0)
    if ($hasLocalMain) {
        Invoke-Git -Arguments @("switch", "main")
    }
    else {
        Invoke-Git -Arguments @("switch", "--track", "-c", "main", "origin/main")
    }
    Invoke-Git -Arguments @("pull", "--ff-only", "origin", "main")
}
else {
    $currentBranch = (& git -C $script:RepoRoot branch --show-current).Trim()
    if ($currentBranch -ne "main") {
        throw "-NoUpdate requires the current branch to be main. Current branch: $currentBranch"
    }
}

$commit = (& git -C $script:RepoRoot rev-parse HEAD).Trim()
Write-Host "Repositorio: $script:RepoRoot"
Write-Host "Rama: main"
Write-Host "Commit: $commit"

# Load a local-only env file, then apply explicit parameters and safe defaults.
if (-not [string]::IsNullOrWhiteSpace($EnvFile)) {
    $envPath = if ([IO.Path]::IsPathRooted($EnvFile)) {
        $EnvFile
    }
    else {
        Join-Path $script:RepoRoot $EnvFile
    }
    if (Test-Path -LiteralPath $envPath -PathType Leaf) {
        Import-SimpleEnvFile -Path $envPath
        Write-Host "Configuración local cargada desde: $envPath (valores existentes en la shell tienen prioridad)"
    }
    else {
        Write-Host "No se encontró $envPath; se usarán las variables ya definidas y los valores por defecto."
    }
}

Set-ProcessEnvOverride -Name "CAMPAIGN_MANAGER_REAL_LLM_BASE_URL" -Value $BaseUrl
Set-ProcessEnvOverride -Name "CAMPAIGN_MANAGER_OLLAMA_BASE_URL" -Value $BaseUrl
Set-ProcessEnvOverride -Name "CAMPAIGN_MANAGER_REAL_LLM_MODEL" -Value $Model
Set-ProcessEnvOverride -Name "CAMPAIGN_MANAGER_LLM_INTENT_MODEL" -Value $IntentModel
Set-ProcessEnvOverride -Name "CAMPAIGN_MANAGER_LLM_EXTRACTION_MODEL" -Value $ExtractionModel
Set-ProcessEnvOverride -Name "CAMPAIGN_MANAGER_LLM_MECHANICS_MODEL" -Value $MechanicsModel
Set-ProcessEnvOverride -Name "CAMPAIGN_MANAGER_LLM_NARRATIVE_MODEL" -Value $NarrativeModel
Set-ProcessEnvOverride -Name "CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT" -Value $TimeoutSeconds
if (-not [string]::IsNullOrWhiteSpace($Think)) {
    Set-ProcessEnvOverride -Name "CAMPAIGN_MANAGER_REAL_LLM_THINK" -Value $Think
    Set-ProcessEnvOverride -Name "CAMPAIGN_MANAGER_OLLAMA_THINK" -Value $Think
}
Set-ProcessEnvOverride -Name "CAMPAIGN_MANAGER_REAL_LLM_HARDWARE" -Value $HardwareLabel

Set-ProcessEnvDefault -Name "CAMPAIGN_MANAGER_REAL_LLM_BASE_URL" -Value "http://localhost:11434"
Set-ProcessEnvDefault -Name "CAMPAIGN_MANAGER_OLLAMA_BASE_URL" -Value $env:CAMPAIGN_MANAGER_REAL_LLM_BASE_URL
Set-ProcessEnvDefault -Name "CAMPAIGN_MANAGER_REAL_LLM_MODEL" -Value "gemma4:26b"
Set-ProcessEnvDefault -Name "CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT" -Value "120"
Set-ProcessEnvDefault -Name "CAMPAIGN_MANAGER_GIT_COMMIT" -Value $commit

if (-not [string]::IsNullOrWhiteSpace($ScenarioId)) {
    Set-ProcessEnvOverride -Name "CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID" -Value $ScenarioId
}
if (-not [string]::IsNullOrWhiteSpace($CompoundScenarioId)) {
    Set-ProcessEnvOverride -Name "CAMPAIGN_MANAGER_REAL_LLM_COMPOUND_SCENARIO_ID" -Value $CompoundScenarioId
}

$baseUrlValue = $env:CAMPAIGN_MANAGER_REAL_LLM_BASE_URL.TrimEnd("/")
$models = @($env:CAMPAIGN_MANAGER_REAL_LLM_MODEL)
foreach ($name in @(
    "CAMPAIGN_MANAGER_LLM_INTENT_MODEL",
    "CAMPAIGN_MANAGER_LLM_EXTRACTION_MODEL",
    "CAMPAIGN_MANAGER_LLM_MECHANICS_MODEL",
    "CAMPAIGN_MANAGER_LLM_NARRATIVE_MODEL"
)) {
    $value = [Environment]::GetEnvironmentVariable($name, "Process")
    if (-not [string]::IsNullOrWhiteSpace($value)) {
        $models += $value
    }
}

if (-not $SkipOllamaPreflight) {
    Invoke-OllamaPreflight -Url $baseUrlValue -RequiredModels $models
}

# Ensure each run has an independent, non-overwriting result directory.
$timestamp = Get-Date -Format "yyyyMMdd-HHmmssfff"
$shortCommit = $commit.Substring(0, [Math]::Min(8, $commit.Length))
$resultsPath = Join-Path $script:RepoRoot $ResultsRoot
$runDirectory = Join-Path $resultsPath "$timestamp-$shortCommit"
$reportDirectory = Join-Path $runDirectory "reports"
New-Item -ItemType Directory -Force -Path $reportDirectory | Out-Null

Set-ProcessEnvOverride -Name "CAMPAIGN_MANAGER_REAL_LLM_REPORT_DIR" -Value $reportDirectory
Set-ProcessEnvOverride -Name "CAMPAIGN_MANAGER_REAL_LLM_REPORT_PATH" -Value (Join-Path $reportDirectory "semantic-holdout.json")
Set-ProcessEnvOverride -Name "CAMPAIGN_MANAGER_REAL_LLM_COMPOUND_REPORT_PATH" -Value (Join-Path $reportDirectory "compound-intent.json")

# Synchronize dependencies without changing user-managed Python installations.
if (-not $SkipDependencySync) {
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) {
        Push-Location $script:RepoRoot
        try {
            & uv sync --group test --no-lock
            if ($LASTEXITCODE -ne 0) {
                throw "uv sync --group test failed with exit code $LASTEXITCODE"
            }
        }
        finally {
            Pop-Location
        }
    }
    else {
        $systemPython = Get-Command python -ErrorAction SilentlyContinue
        if (-not $systemPython) {
            throw "Python 3.12+ is required. Install Python or uv and retry."
        }
        Push-Location $script:RepoRoot
        try {
            & python -m venv .venv
            if ($LASTEXITCODE -ne 0) {
                throw "python -m venv failed with exit code $LASTEXITCODE"
            }
            $venvPython = Get-VenvPython
            if (-not $venvPython) {
                throw "No se encontró el Python del entorno virtual recién creado."
            }
            & $venvPython -m pip install --upgrade pip
            if ($LASTEXITCODE -ne 0) {
                throw "pip upgrade failed with exit code $LASTEXITCODE"
            }
            & $venvPython -m pip install -e . "pytest==9.2.0" "pytest-cov==7.1.0" "httpx2==2.16.0"
            if ($LASTEXITCODE -ne 0) {
                throw "Installing project/test dependencies failed with exit code $LASTEXITCODE"
            }
        }
        finally {
            Pop-Location
        }
    }
}

$python = Get-VenvPython
if (-not $python) {
    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if (-not $systemPython) {
        throw "No se encuentra Python. Ejecuta el script sin -SkipDependencySync o instala Python 3.12+."
    }
    $python = $systemPython.Source
}

$junitPath = Join-Path $runDirectory "junit.xml"
$logPath = Join-Path $runDirectory "pytest.log"
$summaryScript = Join-Path $script:RepoRoot "scripts/ollama_test_report.py"

$pythonVersionCheck = & $python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "Campaign-Manager requires Python 3.12 or newer."
}

Write-Host ""
Write-Host "Modelo común: $env:CAMPAIGN_MANAGER_REAL_LLM_MODEL"
Write-Host "Endpoint: $baseUrlValue"
Write-Host "Timeout por defecto (segundos): $env:CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT"
Write-Host "Resultados: $runDirectory"
Write-Host "Ejecutando todos los tests marcados como real_llm..."
Write-Host ""

Push-Location $script:RepoRoot
try {
    $pytestArguments = @(
        "-m", "pytest",
        "-m", "real_llm",
        "-v",
        "--durations=25",
        "--junitxml", $junitPath
    )
    & $python @pytestArguments 2>&1 | Tee-Object -FilePath $logPath
    $pytestExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

$reportArguments = @(
    $summaryScript,
    "--junit-xml", $junitPath,
    "--output-dir", $runDirectory,
    "--commit", $commit
)
& $python @reportArguments
$reportExitCode = $LASTEXITCODE

Write-Host ""
if ($reportExitCode -eq 0) {
    Write-Host "Reporte generado:"
    Write-Host "  $runDirectory/summary.md"
    Write-Host "  $runDirectory/summary.json"
}
else {
    Write-Warning "No se pudo generar el resumen estadístico (exit code $reportExitCode). Consulta $logPath."
}

if ($pytestExitCode -ne 0) {
    Write-Host "ERROR: Los tests reales de Ollama han fallado (exit code $pytestExitCode). El log y el reporte se han conservado en $runDirectory."
    exit $pytestExitCode
}
if ($reportExitCode -ne 0) {
    exit $reportExitCode
}

Write-Host "Todos los tests reales de Ollama han terminado correctamente."
exit 0
