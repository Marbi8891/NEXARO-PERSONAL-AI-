<#
.SYNOPSIS
  Prueba de humo de una imagen candidata contra el Ollama REAL, con datos temporales.

.DESCRIPTION
  Arranca la imagen en un contenedor temporal (127.0.0.1:<Port>, endurecido como en compose.yaml)
  sobre un volumen temporal y conectado a la red de Ollama. Comprueba: healthcheck de Docker,
  /api/health (Ollama y modelo), login, una respuesta real del modelo, el panel de operaciones,
  reinicio del contenedor y persistencia de la conversación. No toca nexaro-personal-ai_nexaro_data
  ni el contenedor nexaro-backend. Borra solo lo que crea (etiqueta nexaro.test=<id>).

  Úsalo antes de desplegar una imagen nueva (DEPLOYMENT.md).

.EXAMPLE
  pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\smoke_isolated.ps1 -Image nexaro-personal-ai-backend:v1-candidate
#>
[CmdletBinding()]
param(
    [string]$Image = 'nexaro-personal-ai-backend:v1-candidate',
    [string]$Network = 'ollama-local_default',
    [string]$Model = 'qwen2.5:3b',
    [int]$Port = 8093,
    [int]$TimeoutSeconds = 300
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'backup\common.ps1')

$run = Get-Date -Format 'yyyyMMddHHmmss'
$name = "nexaro-smoke-$run"
$volume = "nexaro-smoke-$run"
$base = "http://127.0.0.1:$Port"
$origin = @{ Origin = $base }
$email = 'smoke@example.com'
$password = [Convert]::ToBase64String((1..18 | ForEach-Object { [byte](Get-Random -Maximum 256) }))
$results = [ordered]@{}
$failed = 0
function Check([string]$Label, [bool]$Ok, [string]$Detail = '') {
    $script:results[$Label] = if ($Ok) { "PASS $Detail" } else { "FAIL $Detail" }
    if (-not $Ok) { $script:failed++ }
    Write-Host ("  {0,-5} {1} {2}" -f ($(if ($Ok) { 'OK' } else { 'FALLO' })), $Label, $Detail)
}
function Wait-Healthy {
    for ($i = 0; $i -lt 60; $i++) {
        $h = (& docker inspect -f '{{.State.Health.Status}}' $name 2>$null | Out-String).Trim()
        if ($h -eq 'healthy') { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

try {
    Assert-Docker
    Invoke-Docker @('volume', 'create', '--label', "nexaro.test=$run", $volume) | Out-Null
    Invoke-Docker @('run', '-d', '--name', $name, '--label', "nexaro.test=$run", '--network', $Network,
        '-p', "127.0.0.1:${Port}:8000", '--read-only', '--tmpfs', '/tmp:size=64m', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges', '--pids-limit', '200', '--memory', '1g', '--cpus', '2',
        '-v', "${volume}:/data", '-e', 'DATABASE_PATH=/data/nexaro.db', '-e', 'OLLAMA_BASE_URL=http://ollama:11434',
        '-e', "OLLAMA_MODEL=$Model", '-e', "ALLOWED_ORIGINS=$base", '-e', 'API_DOCS=false',
        '-e', 'BACKUP_STATUS_PATH=/data/backup-status.json', $Image) | Out-Null
    Check 'healthcheck-docker' (Wait-Healthy)

    $health = $null
    for ($i = 0; $i -lt 20 -and -not $health; $i++) {
        try { $health = Invoke-RestMethod "$base/api/health" -TimeoutSec 15 } catch { Start-Sleep -Seconds 3 }
    }
    Check 'ollama-y-modelo' ($health.status -eq 'ok' -and $health.model -eq 'ready') ($health | ConvertTo-Json -Compress)

    $seed = @'
import sys
from pathlib import Path
from nexaro_core.database import Database
from nexaro_core.identity import create_user
with Database(Path("/data/nexaro.db")).connect() as c:
    uid = create_user(c, sys.argv[1], sys.argv[2], approved=True)
    c.execute("UPDATE users SET role = 'admin' WHERE id = ?", (uid,))
'@
    $seedFile = Join-Path ([System.IO.Path]::GetTempPath()) "nexaro-smoke-$run.py"
    [System.IO.File]::WriteAllText($seedFile, $seed)
    try { Invoke-Docker -Arguments @('exec', '-i', $name, 'python', '-', $email, $password) -StdinFile $seedFile | Out-Null }
    finally { Remove-Item -LiteralPath $seedFile -Force }

    $s = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $null = Invoke-RestMethod -Method Post "$base/api/auth/login" -WebSession $s -Headers $origin -ContentType 'application/json' `
        -Body (@{ email = $email; password = $password } | ConvertTo-Json)
    Check 'login' $true

    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    $chat = Invoke-RestMethod -Method Post "$base/api/chat" -WebSession $s -Headers $origin -ContentType 'application/json' `
        -TimeoutSec $TimeoutSeconds -Body (@{ message = 'Responde solo con la palabra: listo' } | ConvertTo-Json)
    $watch.Stop()
    Check 'respuesta-real-ia' ([bool]$chat.answer) ("{0} ms, «{1}»" -f $watch.ElapsedMilliseconds, ($chat.answer -replace '\s+', ' ').Substring(0, [Math]::Min(60, $chat.answer.Length)))

    $status = Invoke-RestMethod "$base/api/admin/status" -WebSession $s
    Check 'panel-operaciones' ($status.database.status -eq 'ok' -and $status.ollama.status -eq 'ok') ("esquema v$($status.database.schema_version), memoria $($status.system.memory.percent) %")

    Invoke-Docker @('restart', $name) | Out-Null
    Check 'healthcheck-tras-reinicio' (Wait-Healthy)
    $null = Invoke-RestMethod -Method Post "$base/api/auth/login" -WebSession $s -Headers $origin -ContentType 'application/json' `
        -Body (@{ email = $email; password = $password } | ConvertTo-Json)
    $conv = Invoke-RestMethod "$base/api/conversations/$($chat.conversation_id)" -WebSession $s
    Check 'persistencia-tras-reinicio' (@($conv.messages).Count -eq 2)

    $ports = (& docker port $name | Out-String).Trim()
    Check 'solo-loopback' ($ports -notmatch '0\.0\.0\.0|\[::\]') $ports
} catch {
    $failed++
    $results['error'] = $_.Exception.Message
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
} finally {
    & docker rm -f $name *> $null
    foreach ($v in (& docker volume ls -q --filter "label=nexaro.test=$run")) { if ($v -like 'nexaro-smoke-*') { & docker volume rm $v *> $null } }
}

Write-Host ''
$results.GetEnumerator() | ForEach-Object { Write-Host ("{0,-28} {1}" -f $_.Key, $_.Value) }
if ($failed -eq 0) { Write-Host 'SMOKE AISLADO: PASS'; exit 0 }
Write-Host "SMOKE AISLADO: FAIL ($failed)" -ForegroundColor Red
exit 1
