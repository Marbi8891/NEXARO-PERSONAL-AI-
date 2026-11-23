<#
.SYNOPSIS
  Restaura una copia de NEXARO en un volumen Docker.

.DESCRIPTION
  Por defecto restaura en un volumen NUEVO (nexaro-restore-<fecha>) y no toca el volumen en uso:
  sirve para probar la copia o arrancar un backend de prueba encima. Antes de escribir verifica la
  copia (verify_backup.ps1) y se niega a usar un volumen que ya tenga nexaro.db.

  Restaurar sobre el volumen REAL exige -IntoLiveVolume, el backend parado, escribir RESTAURAR
  cuando se pide y hace antes una copia 'pre-restore' del estado actual. La base anterior no se
  borra: se renombra dentro del volumen a nexaro.replaced-<fecha>.db.

.EXAMPLE
  pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\restore_nexaro.ps1 -Path C:\Users\pc\NEXARO-Backups\nexaro-20261123-030000-daily
.EXAMPLE
  # Restauración real (con el backend parado: docker stop nexaro-backend)
  pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\restore_nexaro.ps1 -Path ... -IntoLiveVolume
#>
[CmdletBinding()]
param(
    [string]$Path = '',
    [string]$BackupRoot = $(if ($env:NEXARO_BACKUP_ROOT) { $env:NEXARO_BACKUP_ROOT } else { Join-Path $env:USERPROFILE 'NEXARO-Backups' }),
    [string]$TargetVolume = '',
    [switch]$IntoLiveVolume,
    [string]$LiveVolume = 'nexaro-personal-ai_nexaro_data',
    [string]$Container = 'nexaro-backend',
    [string]$Image = 'nexaro-personal-ai-backend',
    [switch]$Yes  # solo para pruebas automatizadas sobre volúmenes NO reales
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'backup\common.ps1')

Assert-Docker
$dir = Resolve-BackupPath $Path $BackupRoot
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$img = Get-ContainerImage $Container $Image

Write-Step "1/4 Verificación previa de $dir"
& (Join-Path $PSScriptRoot 'verify_backup.ps1') -Path $dir -Image $img -Container $Container
if ($LASTEXITCODE -ne 0) { throw 'La copia no es válida: no se restaura' }

if ($IntoLiveVolume) {
    if ($TargetVolume -and $TargetVolume -ne $LiveVolume) { throw '-IntoLiveVolume y -TargetVolume son incompatibles' }
    $TargetVolume = $LiveVolume
    if ($Yes) { throw '-Yes no se admite para el volumen real: la confirmación es manual' }
    if (Test-ContainerRunning $Container) { throw "Para $Container antes de restaurar: docker stop $Container" }
    Write-Step '2/4 Copia de seguridad del estado actual (pre-restore)'
    & (Join-Path $PSScriptRoot 'backup_nexaro.ps1') -BackupRoot $BackupRoot -Reason pre-restore -Container $Container -Volume $LiveVolume -Image $img -NoPrune
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo copiar el estado actual: no se restaura' }
    $answer = Read-Host "Se sustituirá la base de $LiveVolume por la de $(Split-Path $dir -Leaf). Escribe RESTAURAR"
    if ($answer -cne 'RESTAURAR') { throw 'Cancelado: no se ha cambiado nada' }
} else {
    if (-not $TargetVolume) { $TargetVolume = "nexaro-restore-$stamp" }
    if ($TargetVolume -eq $LiveVolume) { throw "Para restaurar sobre $LiveVolume usa -IntoLiveVolume" }
    Write-Step "2/4 Volumen de destino $TargetVolume (nuevo, no es el real)"
    if (-not (Test-VolumeExists $TargetVolume)) {
        Invoke-Docker @('volume', 'create', '--label', 'nexaro.restore=true', $TargetVolume) | Out-Null
    }
}

Write-Step "3/4 Copia de nexaro.db a $TargetVolume"
# Contenedor temporal sin red. La copia se monta en solo lectura; en el volumen de destino la base
# anterior (solo con -IntoLiveVolume) se renombra, nunca se borra.
$live = if ($IntoLiveVolume) { '1' } else { '0' }
$restoreScript = @"
import os, shutil, sys
live = sys.argv[1] == '1'
db = '/data/nexaro.db'
if os.path.exists(db):
    if not live:
        sys.exit('el volumen de destino ya tiene nexaro.db: elige otro (no se sobrescribe)')
    os.replace(db, '/data/nexaro.replaced-$stamp.db')
for extra in ('-wal', '-shm', '-journal'):
    if os.path.exists(db + extra):
        os.replace(db + extra, '/data/nexaro.replaced-$stamp.db' + extra)
shutil.copyfile('/backup/nexaro.db', db + '.restoring')
os.chmod(db + '.restoring', 0o600)
os.replace(db + '.restoring', db)
print('restaurado')
"@
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) "nexaro-restore-$stamp.py"
[System.IO.File]::WriteAllText($tmp, $restoreScript)
try {
    $out = Get-Content -LiteralPath $tmp -Raw | & docker run --rm -i --network none --read-only --cap-drop ALL `
        --security-opt no-new-privileges --user 10001:10001 --entrypoint python `
        -v "${TargetVolume}:/data" -v "$(ConvertTo-DockerPath $dir):/backup:ro" $img - $live 2>&1
    if ($LASTEXITCODE -ne 0) { throw "La restauración falló: $(($out | Out-String).Trim())" }
} finally {
    Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
}

Write-Step '4/4 Comprobación de la base restaurada'
$check = Invoke-HelperInContainer -Image $img -Mounts @("${TargetVolume}:/data:ro") -HelperArgs @('inspect', '/data/nexaro.db', '--immutable') -AllowFailure
if ($check.ExitCode -ne 0) { throw "La base restaurada no supera la verificación: $($check.Output)" }
Write-Ok $check.Output
Write-Host ''
Write-Host "RESTAURADO en el volumen $TargetVolume"
if (-not $IntoLiveVolume) {
    Write-Host "Para probarlo sin tocar el real: docker run --rm -d --name nexaro-restore-check -p 127.0.0.1:8011:8000 -v ${TargetVolume}:/data $img"
} else {
    Write-Host "Arranca el backend: docker start $Container   (la base anterior quedó como nexaro.replaced-$stamp.db)"
}
exit 0
