<#
.SYNOPSIS
  Verifica una copia de NEXARO: SHA-256 de cada archivo, integridad SQLite, claves foráneas y
  coincidencia con el manifiesto. Solo lee. Código de salida 0 = copia válida.

.EXAMPLE
  pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\verify_backup.ps1            # la más reciente
.EXAMPLE
  pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\verify_backup.ps1 -Path C:\Users\pc\NEXARO-Backups\nexaro-20261123-030000-daily
#>
[CmdletBinding()]
param(
    [string]$Path = '',
    [string]$BackupRoot = $(if ($env:NEXARO_BACKUP_ROOT) { $env:NEXARO_BACKUP_ROOT } else { Join-Path $env:USERPROFILE 'NEXARO-Backups' }),
    [string]$Image = 'nexaro-personal-ai-backend',
    [string]$Container = 'nexaro-backend'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'backup\common.ps1')

$failures = 0
function Fail([string]$Message) { Write-Host "  FALLO $Message" -ForegroundColor Red; $script:failures++ }

$dir = Resolve-BackupPath $Path $BackupRoot
Write-Step "Copia: $dir"
$manifest = Get-Content -LiteralPath (Join-Path $dir 'manifest.json') -Raw | ConvertFrom-Json

Write-Step '1/3 Sumas SHA-256'
$sumsFile = Join-Path $dir 'SHA256SUMS'
if (-not (Test-Path -LiteralPath $sumsFile)) { Fail 'falta SHA256SUMS' } else {
    $listed = @{}
    foreach ($line in Get-Content -LiteralPath $sumsFile) {
        if (-not $line.Trim()) { continue }
        $hash, $rel = $line -split '  ', 2
        $listed[$rel] = $true
        $file = Join-Path $dir ($rel -replace '/', '\')
        if (-not (Test-Path -LiteralPath $file)) { Fail "falta $rel"; continue }
        if ((Get-Sha256 $file) -ne $hash) { Fail "hash distinto: $rel" } else { Write-Ok $rel }
    }
    if (-not $listed.ContainsKey('nexaro.db')) { Fail 'SHA256SUMS no incluye nexaro.db' }
    if (@($manifest.files).Count -ne $listed.Count) { Fail 'el manifiesto y SHA256SUMS no coinciden' }
}

Write-Step '2/3 Integridad SQLite y claves foráneas (contenedor sin red, copia en solo lectura)'
Assert-Docker
$img = Get-ContainerImage $Container $Image
$check = Invoke-HelperInContainer -Image $img -Mounts @("$(ConvertTo-DockerPath $dir):/backup:ro") `
    -HelperArgs @('inspect', '/backup/nexaro.db', '--immutable') -AllowFailure
try { $report = $check.Output | ConvertFrom-Json } catch { $report = $null }
if ($null -eq $report) { Fail "no se pudo inspeccionar la base: $($check.Output)" } else {
    if ($report.integrity -ne 'ok') { Fail "integrity_check: $($report.integrity)" } else { Write-Ok 'integrity_check = ok' }
    if ($report.foreign_key_errors -ne 0) { Fail "$($report.foreign_key_errors) errores de claves foráneas" } else { Write-Ok 'foreign_key_check sin errores' }

    Write-Step '3/3 Coincidencia con el manifiesto'
    if ($report.schema_version -ne $manifest.database.schema_version) { Fail 'versión de esquema distinta del manifiesto' } else { Write-Ok "esquema v$($report.schema_version)" }
    foreach ($prop in $manifest.database.counts.PSObject.Properties) {
        $now = $report.counts.($prop.Name)
        if ($now -ne $prop.Value) { Fail "$($prop.Name): $now filas (manifiesto: $($prop.Value))" }
    }
    if ($failures -eq 0) { Write-Ok "recuentos: $($report.counts | ConvertTo-Json -Compress)" }
}

Write-Host ''
if ($failures -eq 0) { Write-Host "COPIA VÁLIDA: $dir"; exit 0 }
Write-Host "COPIA NO VÁLIDA: $failures problemas" -ForegroundColor Red
exit 1
