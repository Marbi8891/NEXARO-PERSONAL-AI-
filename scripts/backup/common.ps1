# Shared functions for backup_nexaro.ps1, verify_backup.ps1 and restore_nexaro.ps1.
# Compatible with Windows PowerShell 5.1 and PowerShell 7. Dot-sourced; defines no global state.
# Never runs `docker compose down`, never deletes volumes and never writes to the live database.

Set-StrictMode -Version 3.0

$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script:HelperPath = Join-Path $PSScriptRoot 'nexaro_backup_helper.py'
$script:BackupNamePattern = '^nexaro-\d{8}-\d{6}-(daily|pre-migration|pre-update|pre-restore|manual)$'
$script:SensitivePattern = '(?i)(secret|token|password|passwd|api_key|apikey|private|credential|aws_access|aws_session)'

function Write-Step([string]$Message) { Write-Host "==> $Message" }
function Write-Ok([string]$Message) { Write-Host "  OK    $Message" }
function Write-Warn2([string]$Message) { Write-Host "  AVISO $Message" -ForegroundColor Yellow }

function Assert-Docker {
    $null = Get-Command docker -ErrorAction Stop
    & docker info --format '{{.ServerVersion}}' *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Docker no responde (¿Docker Desktop arrancado?)' }
}

function Invoke-Docker {
    # Runs docker and throws if it fails. Returns stdout as a single string.
    param([Parameter(Mandatory)][string[]]$Arguments, [string]$StdinFile)
    if ($StdinFile) {
        $out = Get-Content -LiteralPath $StdinFile -Raw | & docker @Arguments
    } else {
        $out = & docker @Arguments
    }
    if ($LASTEXITCODE -ne 0) { throw "docker $($Arguments -join ' ') falló (código $LASTEXITCODE)" }
    return ($out | Out-String).Trim()
}

function Test-ContainerRunning([string]$Name) {
    $state = & docker inspect -f '{{.State.Running}}' $Name 2>$null
    return ($LASTEXITCODE -eq 0 -and "$state".Trim() -eq 'true')
}

function Test-ContainerExists([string]$Name) {
    & docker container inspect $Name *> $null
    return ($LASTEXITCODE -eq 0)
}

function Test-VolumeExists([string]$Name) {
    & docker volume inspect $Name *> $null
    return ($LASTEXITCODE -eq 0)
}

function Get-FullPath([string]$Path) {
    return [System.IO.Path]::GetFullPath($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path))
}

function Assert-OutsideRepo([string]$Path) {
    # Backups must never end up inside the git checkout (they hold personal data).
    $full = (Get-FullPath $Path).TrimEnd('\') + '\'
    $repo = $script:RepoRoot.TrimEnd('\') + '\'
    if ($full.StartsWith($repo, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "El destino de las copias ($Path) está dentro del repositorio: usa una carpeta externa"
    }
}

function ConvertTo-DockerPath([string]$Path) {
    # Docker Desktop accepts C:\... paths in -v; forward slashes avoid escaping surprises.
    return (Get-FullPath $Path) -replace '\\', '/'
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-RedactedEnv([string]$Path) {
    # Copy of an .env file with the values of sensitive-looking keys replaced.
    $lines = foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { $line; continue }
        $key, $value = $line -split '=', 2
        if ($key -match $script:SensitivePattern -and $value.Trim()) { "$key=<redacted>" } else { $line }
    }
    return ($lines -join "`n")
}

function Get-BackupDirectories([string]$Root) {
    if (-not (Test-Path -LiteralPath $Root)) { return @() }
    return @(Get-ChildItem -LiteralPath $Root -Directory |
        Where-Object { $_.Name -match $script:BackupNamePattern -and (Test-Path -LiteralPath (Join-Path $_.FullName 'manifest.json')) } |
        Sort-Object Name)
}

function Resolve-BackupPath([string]$Path, [string]$Root) {
    if ($Path) {
        $full = Get-FullPath $Path
        if (-not (Test-Path -LiteralPath (Join-Path $full 'manifest.json'))) { throw "No es una copia de NEXARO: $Path" }
        return $full
    }
    $all = @(Get-BackupDirectories $Root)  # @(): sin copias, la función devuelve $null y no @()
    if ($all.Count -eq 0) { throw "No hay copias en $Root" }
    return $all[-1].FullName
}

function Invoke-HelperInContainer {
    # Runs nexaro_backup_helper.py in a throwaway container: no network, read-only root, no caps.
    param(
        [Parameter(Mandatory)][string]$Image,
        [Parameter(Mandatory)][string[]]$Mounts,
        [Parameter(Mandatory)][string[]]$HelperArgs,
        [switch]$AllowFailure
    )
    $dockerArgs = @('run', '--rm', '-i', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges', '--tmpfs', '/tmp', '--entrypoint', 'python')
    foreach ($m in $Mounts) { $dockerArgs += @('-v', $m) }
    $dockerArgs += @($Image, '-')
    $dockerArgs += $HelperArgs
    $out = Get-Content -LiteralPath $script:HelperPath -Raw | & docker @dockerArgs
    $code = $LASTEXITCODE
    if ($code -ne 0 -and -not $AllowFailure) { throw "El helper falló (código $code): $out" }
    return [pscustomobject]@{ Output = ($out | Out-String).Trim(); ExitCode = $code }
}

function Get-ContainerImage([string]$Container, [string]$Fallback) {
    if (Test-ContainerExists $Container) {
        return (Invoke-Docker @('inspect', '-f', '{{.Image}}', $Container))
    }
    return $Fallback
}

function Set-TreeReadOnly([string]$Path, [bool]$ReadOnly) {
    Get-ChildItem -LiteralPath $Path -Recurse -File | ForEach-Object { $_.IsReadOnly = $ReadOnly }
}
