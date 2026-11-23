<#
.SYNOPSIS
  Copia de seguridad verificada de NEXARO (base SQLite + configuración sin secretos + modelos).

.DESCRIPTION
  Crea <BackupRoot>\nexaro-<fecha>-<motivo>\ con:
    nexaro.db            copia consistente (API de backup de SQLite; segura con la app en marcha)
    config\              compose.yaml, .env.example y .env REDACTADO (sin valores sensibles)
    models.txt           `ollama list` y modelo configurado
    container.json       imagen, versión del esquema y variables NO sensibles del backend
    manifest.json        motivo, commit, recuentos, integridad y SHA-256 de cada archivo
    SHA256SUMS

  Nunca sobrescribe una copia (el nombre lleva fecha y hora; si existe, falla), marca los archivos
  como solo lectura y nunca escribe en la base viva. Con el backend parado lee el volumen en modo
  solo lectura. Retención: conserva las -Keep más recientes de cada motivo (solo carpetas creadas
  por este script). Ver BACKUP_RESTORE.md.

.EXAMPLE
  pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\backup_nexaro.ps1
.EXAMPLE
  pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\backup_nexaro.ps1 -Reason pre-update -Keep 20
#>
[CmdletBinding()]
param(
    [string]$BackupRoot = $(if ($env:NEXARO_BACKUP_ROOT) { $env:NEXARO_BACKUP_ROOT } else { Join-Path $env:USERPROFILE 'NEXARO-Backups' }),
    [ValidateSet('daily', 'pre-migration', 'pre-update', 'pre-restore', 'manual')]
    [string]$Reason = 'manual',
    [string]$Container = 'nexaro-backend',
    [string]$Volume = 'nexaro-personal-ai_nexaro_data',
    [string]$Image = 'nexaro-personal-ai-backend',
    [string]$OllamaContainer = 'ollama',
    [string]$EnvFile = '',
    [ValidateRange(1, 1000)][int]$Keep = 14,
    [switch]$NoPrune
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'backup\common.ps1')

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$name = "nexaro-$stamp-$Reason"
$logFile = $null
$work = $null
$result = [ordered]@{ name = $name; reason = $Reason; started_at = (Get-Date).ToString('o'); ok = $false }

try {
    Assert-Docker
    Assert-OutsideRepo $BackupRoot
    if (-not (Test-Path -LiteralPath $BackupRoot)) { New-Item -ItemType Directory -Path $BackupRoot | Out-Null }
    $BackupRoot = Get-FullPath $BackupRoot
    $logFile = Join-Path $BackupRoot 'backup-log.jsonl'
    $target = Join-Path $BackupRoot $name
    if (Test-Path -LiteralPath $target) { throw "Ya existe ${target}: no se sobrescribe" }
    $partial = "$target.partial"
    if (Test-Path -LiteralPath $partial) { throw "Existe un intento a medias: $partial (revísalo y bórralo a mano)" }
    New-Item -ItemType Directory -Path $partial | Out-Null
    $work = $partial  # solo a partir de aquí la limpieza ante errores puede borrarlo: es nuestro
    New-Item -ItemType Directory -Path (Join-Path $work 'config') | Out-Null

    if (-not (Test-VolumeExists $Volume)) { throw "No existe el volumen $Volume" }
    $img = Get-ContainerImage $Container $Image
    $running = Test-ContainerRunning $Container

    Write-Step "1/5 Copia consistente de la base ($(if ($running) { 'backend en marcha' } else { 'backend parado: volumen en solo lectura' }))"
    $dbCopy = Join-Path $work 'nexaro.db'
    if ($running) {
        $tmpName = ".nexaro-backup-$stamp.db"
        try {
            $out = Invoke-Docker -Arguments @('exec', '-i', $Container, 'python', '-', 'snapshot', '/data/nexaro.db', "/data/$tmpName") -StdinFile $script:HelperPath
            Invoke-Docker @('cp', "${Container}:/data/$tmpName", $dbCopy) | Out-Null
        } finally {
            Get-Content -LiteralPath $script:HelperPath -Raw | & docker exec -i $Container python - remove "/data/$tmpName" | Out-Null
        }
    } else {
        $snap = Invoke-HelperInContainer -Image $img -Mounts @("${Volume}:/data:ro", "$(ConvertTo-DockerPath $work):/backup") `
            -HelperArgs @('snapshot', '/data/nexaro.db', '/backup/nexaro.db', '--immutable')  # nadie escribe: backend parado, volumen :ro
        $out = $snap.Output
    }
    if (-not (Test-Path -LiteralPath $dbCopy)) { throw 'La copia de la base no se ha creado' }

    Write-Step '2/5 Integridad de la copia'
    $check = Invoke-HelperInContainer -Image $img -Mounts @("$(ConvertTo-DockerPath $work):/backup:ro") `
        -HelperArgs @('inspect', '/backup/nexaro.db', '--immutable') -AllowFailure
    $report = $check.Output | ConvertFrom-Json
    if ($check.ExitCode -ne 0 -or $report.integrity -ne 'ok' -or $report.foreign_key_errors -ne 0) {
        throw "La copia no supera la verificación: $($check.Output)"
    }
    Write-Ok "integrity=ok, esquema v$($report.schema_version), $($report.counts | ConvertTo-Json -Compress)"

    Write-Step '3/5 Configuración (sin secretos) y modelos'
    foreach ($file in @('compose.yaml', '.env.example')) {
        $src = Join-Path $script:RepoRoot $file
        if (Test-Path -LiteralPath $src) { Copy-Item -LiteralPath $src -Destination (Join-Path $work 'config') }
    }
    $envPath = if ($EnvFile) { $EnvFile } else { Join-Path $script:RepoRoot '.env' }
    if (Test-Path -LiteralPath $envPath) {
        [System.IO.File]::WriteAllText((Join-Path $work 'config\env.redacted'), (Get-RedactedEnv $envPath))
        Write-Ok '.env copiado con los valores sensibles sustituidos por <redacted>'
    }
    $models = "modelo configurado: (desconocido)"
    if (Test-ContainerExists $Container) {
        $envVars = (Invoke-Docker @('inspect', '-f', '{{json .Config.Env}}', $Container)) | ConvertFrom-Json
        $safeEnv = @($envVars | Where-Object { ($_ -split '=', 2)[0] -notmatch $script:SensitivePattern })
        $model = ($envVars | Where-Object { $_ -like 'OLLAMA_MODEL=*' } | Select-Object -First 1)
        if ($model) { $models = "modelo configurado: $(($model -split '=', 2)[1])" }
        $containerInfo = [ordered]@{ container = $Container; image = $img; env = $safeEnv }
        [System.IO.File]::WriteAllText((Join-Path $work 'container.json'), ($containerInfo | ConvertTo-Json -Depth 4))
    }
    if (Test-ContainerRunning $OllamaContainer) {
        $list = & docker exec $OllamaContainer ollama list 2>&1 | Out-String
        $models += "`n`nollama list ($OllamaContainer):`n$list"
    } else {
        $models += "`n`n(Ollama '$OllamaContainer' no está en marcha: lista de modelos no disponible)"
    }
    [System.IO.File]::WriteAllText((Join-Path $work 'models.txt'), $models)

    Write-Step '4/5 Manifiesto y sumas SHA-256'
    $commit = (& git -C $script:RepoRoot rev-parse HEAD 2>$null | Out-String).Trim()
    $files = Get-ChildItem -LiteralPath $work -Recurse -File | Sort-Object FullName
    $sums = foreach ($f in $files) {
        $rel = $f.FullName.Substring($work.Length + 1) -replace '\\', '/'
        "$(Get-Sha256 $f.FullName)  $rel"
    }
    [System.IO.File]::WriteAllText((Join-Path $work 'SHA256SUMS'), (($sums -join "`n") + "`n"))
    $manifest = [ordered]@{
        format = 1
        name = $name
        reason = $Reason
        created_at = (Get-Date).ToString('o')
        host = $env:COMPUTERNAME
        git_commit = $commit
        image = $img
        volume = $Volume
        backend_running = $running
        database = $report
        files = @($sums)
    }
    [System.IO.File]::WriteAllText((Join-Path $work 'manifest.json'), ($manifest | ConvertTo-Json -Depth 6))

    Rename-Item -LiteralPath $work -NewName $name
    Set-TreeReadOnly $target $true
    Write-Ok "copia en $target"

    Write-Step '5/5 Retención'
    if ($NoPrune) {
        Write-Ok 'retención omitida (-NoPrune)'
    } else {
        $same = @(Get-BackupDirectories $BackupRoot | Where-Object { $_.Name -like "*-$Reason" })
        $excess = $same.Count - $Keep
        if ($excess -gt 0) {
            foreach ($old in ($same | Select-Object -First $excess)) {
                if (Test-Path -LiteralPath (Join-Path $old.FullName '.keep')) { continue }
                Set-TreeReadOnly $old.FullName $false
                Remove-Item -LiteralPath $old.FullName -Recurse -Force
                Write-Ok "retirada la copia antigua $($old.Name)"
            }
        } else {
            Write-Ok "$($same.Count) copias '$Reason' (límite $Keep)"
        }
    }

    $result.ok = $true
    $result.path = $target
    $result.schema_version = $report.schema_version
    $result.counts = $report.counts
    $result.size_bytes = $report.size_bytes
} catch {
    $result.error = $_.Exception.Message
    # Un intento fallido no deja copias parciales de datos personales por ahí.
    if ($work -and (Test-Path -LiteralPath $work)) { Remove-Item -LiteralPath $work -Recurse -Force }
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
} finally {
    $result.finished_at = (Get-Date).ToString('o')
    if ($logFile) {
        Add-Content -LiteralPath $logFile -Value ($result | ConvertTo-Json -Compress -Depth 4) -Encoding UTF8
        [System.IO.File]::WriteAllText((Join-Path $BackupRoot 'last-backup.json'), ($result | ConvertTo-Json -Depth 4))
    }
    # Estado para el panel de operaciones (solo si el backend está en marcha; nunca crítico).
    if ((Get-Command docker -ErrorAction SilentlyContinue) -and (Test-ContainerRunning $Container)) {
        $payload = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes(($result | ConvertTo-Json -Compress -Depth 4)))
        Get-Content -LiteralPath $script:HelperPath -Raw |
            & docker exec -i $Container python - status-write /data/backup-status.json $payload 2>$null | Out-Null
    }
}

if (-not $result.ok) { exit 1 }
exit 0
