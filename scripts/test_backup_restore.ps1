<#
.SYNOPSIS
  Prueba completa de copia y restauración en un entorno TEMPORAL (nunca toca los datos reales).

.DESCRIPTION
  1. Crea un volumen temporal y arranca un backend de prueba (127.0.0.1:<PortA>) con datos
     sintéticos: un administrador, una conversación con mensajes, una organización y un documento.
  2. Copia con el backend en marcha (docker exec) y otra con el backend parado (volumen :ro).
  3. Verifica ambas copias y comprueba que una copia manipulada se detecta.
  4. Restaura en OTRO volumen temporal, arranca un backend nuevo (127.0.0.1:<PortB>) y comprueba:
     arranque, login, conversación con sus mensajes y documento recuperados.
  5. Limpia SOLO lo que ha creado: contenedores nexaro-bkptest-* y volúmenes con la etiqueta
     nexaro.test=<id de esta ejecución>. -KeepArtifacts los conserva para inspeccionarlos.

  Usa la imagen indicada (-Image). Para probar el código del repositorio, constrúyela antes:
    docker build -t nexaro-personal-ai-backend:v1-candidate C:\Users\pc\NEXARO-PERSONAL-AI

.EXAMPLE
  pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\test_backup_restore.ps1 -Image nexaro-personal-ai-backend:v1-candidate
#>
[CmdletBinding()]
param(
    [string]$Image = 'nexaro-personal-ai-backend:v1-candidate',
    [string]$WorkDir = (Join-Path ([System.IO.Path]::GetTempPath()) 'nexaro-backup-test'),
    [int]$PortA = 8091,
    [int]$PortB = 8092,
    [switch]$KeepArtifacts
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'backup\common.ps1')

$run = Get-Date -Format 'yyyyMMddHHmmss'
$srcVolume = "nexaro-bkptest-src-$run"
$dstVolume = "nexaro-bkptest-dst-$run"
$srcName = "nexaro-bkptest-src-$run"
$dstName = "nexaro-bkptest-dst-$run"
$backupRoot = Join-Path $WorkDir $run
$email = 'restore-test@example.com'
$password = [Convert]::ToBase64String((1..18 | ForEach-Object { [byte](Get-Random -Maximum 256) }))
$results = [ordered]@{}
$failed = 0

function Check([string]$Name, [bool]$Condition, [string]$Detail = '') {
    $script:results[$Name] = if ($Condition) { 'PASS' } else { "FAIL $Detail" }
    if ($Condition) { Write-Ok "$Name $Detail" } else { Write-Host "  FALLO $Name $Detail" -ForegroundColor Red; $script:failed++ }
}

function Start-Backend([string]$Name, [string]$Volume, [int]$Port) {
    Invoke-Docker @('run', '-d', '--name', $Name, '--label', "nexaro.test=$run",
        '-p', "127.0.0.1:${Port}:8000", '--read-only', '--tmpfs', '/tmp', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges', '-v', "${Volume}:/data",
        '-e', 'DATABASE_PATH=/data/nexaro.db', '-e', 'OLLAMA_BASE_URL=http://127.0.0.1:9',
        '-e', "ALLOWED_ORIGINS=http://127.0.0.1:$Port", '-e', 'API_DOCS=false', $Image) | Out-Null
    for ($i = 0; $i -lt 40; $i++) {
        try {
            $r = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health/live" -TimeoutSec 2
            if ($r.status -eq 'ok') { return $true }
        } catch { Start-Sleep -Milliseconds 750 }
    }
    return $false
}

function New-Session([int]$Port) {
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $body = @{ email = $email; password = $password } | ConvertTo-Json
    $null = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$Port/api/auth/login" -WebSession $session `
        -ContentType 'application/json' -Headers @{ Origin = "http://127.0.0.1:$Port" } -Body $body
    return $session
}

try {
    Assert-Docker
    & docker image inspect $Image *> $null
    if ($LASTEXITCODE -ne 0) { throw "No existe la imagen $Image (constrúyela: docker build -t $Image .)" }
    New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

    Write-Step "Entorno temporal $run (imagen $Image)"
    Invoke-Docker @('volume', 'create', '--label', "nexaro.test=$run", $srcVolume) | Out-Null
    Invoke-Docker @('volume', 'create', '--label', "nexaro.test=$run", $dstVolume) | Out-Null
    Check 'arranque-origen' (Start-Backend $srcName $srcVolume $PortA)

    # Datos sintéticos: usuario y conversación por Python (el chat real necesitaría Ollama);
    # organización y documento por la API HTTP, como lo haría la interfaz.
    $seed = @'
import sys, uuid
from pathlib import Path
from nexaro_core.database import Database
from nexaro_core.identity import create_user
db = Database(Path("/data/nexaro.db"))
with db.connect() as c:
    uid = create_user(c, sys.argv[1], sys.argv[2], approved=True)
    c.execute("UPDATE users SET role = 'admin' WHERE id = ?", (uid,))
    cid = str(uuid.uuid4())
    c.execute("INSERT INTO conversations (id, user_id) VALUES (?, ?)", (cid, uid))
    c.execute("INSERT INTO messages (conversation_id, role, content) VALUES (?, 'user', 'pregunta de prueba de restauracion')", (cid,))
    c.execute("INSERT INTO messages (conversation_id, role, content) VALUES (?, 'assistant', 'respuesta de prueba de restauracion')", (cid,))
print(cid)
'@
    $seedFile = Join-Path $backupRoot 'seed.py'
    [System.IO.File]::WriteAllText($seedFile, $seed)
    $conversationId = Invoke-Docker -Arguments @('exec', '-i', $srcName, 'python', '-', $email, $password) -StdinFile $seedFile
    Remove-Item -LiteralPath $seedFile
    $s = New-Session $PortA
    $h = @{ Origin = "http://127.0.0.1:$PortA" }
    $org = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$PortA/api/organizations" -WebSession $s -Headers $h `
        -ContentType 'application/json' -Body (@{ name = 'Prueba restauracion'; slug = "restore-$run" } | ConvertTo-Json)
    $orgId = $org.id
    if (-not $orgId) { $orgId = $org.organization.id }
    $null = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$PortA/api/organizations/$orgId/documents" -WebSession $s -Headers $h `
        -ContentType 'application/json' -Body (@{ title = 'Manual de prueba'; content = 'El documento de prueba habla de copias de seguridad verificadas.' } | ConvertTo-Json)
    $before = Invoke-RestMethod -Uri "http://127.0.0.1:$PortA/api/conversations/$conversationId" -WebSession $s
    Check 'datos-sinteticos' (@($before.messages).Count -eq 2) "conversación $conversationId"

    Write-Step 'Copia con el backend en marcha'
    & (Join-Path $PSScriptRoot 'backup_nexaro.ps1') -BackupRoot $backupRoot -Reason manual -Container $srcName -Volume $srcVolume -Image $Image -NoPrune -OllamaContainer 'no-existe'
    Check 'backup-en-marcha' ($LASTEXITCODE -eq 0)
    $hot = (Get-BackupDirectories $backupRoot)[-1].FullName

    Write-Step 'Copia con el backend parado (volumen en solo lectura)'
    Invoke-Docker @('stop', $srcName) | Out-Null
    Start-Sleep -Seconds 1  # el nombre de la copia lleva segundos
    & (Join-Path $PSScriptRoot 'backup_nexaro.ps1') -BackupRoot $backupRoot -Reason pre-update -Container $srcName -Volume $srcVolume -Image $Image -NoPrune -OllamaContainer 'no-existe'
    Check 'backup-parado' ($LASTEXITCODE -eq 0)
    $cold = (Get-BackupDirectories $backupRoot | Where-Object { $_.Name -like '*-pre-update' })[-1].FullName

    Write-Step 'Verificación de las dos copias'
    foreach ($b in @($hot, $cold)) {
        & (Join-Path $PSScriptRoot 'verify_backup.ps1') -Path $b -Image $Image -Container $srcName
        Check "verify-$(Split-Path $b -Leaf)" ($LASTEXITCODE -eq 0)
    }
    Check 'copia-solo-lectura' ((Get-Item -LiteralPath (Join-Path $hot 'nexaro.db')).IsReadOnly)

    Write-Step 'Una copia manipulada se detecta'
    $tampered = Join-Path $WorkDir "$run-tampered\nexaro-20000101-000000-manual"
    New-Item -ItemType Directory -Force -Path $tampered | Out-Null
    Copy-Item -Path (Join-Path $hot '*') -Destination $tampered -Recurse
    Set-TreeReadOnly $tampered $false
    Add-Content -LiteralPath (Join-Path $tampered 'models.txt') -Value 'manipulado'
    & (Join-Path $PSScriptRoot 'verify_backup.ps1') -Path $tampered -Image $Image -Container $srcName *> $null
    Check 'manipulacion-detectada' ($LASTEXITCODE -ne 0)

    Write-Step 'Restauración en un volumen temporal distinto'
    & (Join-Path $PSScriptRoot 'restore_nexaro.ps1') -Path $hot -TargetVolume $dstVolume -LiveVolume $srcVolume -Image $Image -Container $srcName
    Check 'restauracion' ($LASTEXITCODE -eq 0)
    $refused = $false
    try {
        & (Join-Path $PSScriptRoot 'restore_nexaro.ps1') -Path $hot -TargetVolume $dstVolume -LiveVolume $srcVolume -Image $Image -Container $srcName *> $null
        $refused = ($LASTEXITCODE -ne 0)
    } catch { $refused = $_.Exception.Message -like '*ya tiene nexaro.db*' }
    Check 'no-sobrescribe-destino' $refused

    Write-Step 'Arranque, login y datos sobre la copia restaurada'
    Check 'arranque-restaurado' (Start-Backend $dstName $dstVolume $PortB)
    $s2 = New-Session $PortB
    Check 'login-restaurado' ($null -ne $s2)
    $after = Invoke-RestMethod -Uri "http://127.0.0.1:$PortB/api/conversations/$conversationId" -WebSession $s2
    $same = (@($after.messages).Count -eq 2) -and ($after.messages[1].content -eq $before.messages[1].content)
    Check 'conversaciones-recuperadas' $same
    $docs = Invoke-RestMethod -Uri "http://127.0.0.1:$PortB/api/organizations/$orgId/documents" -WebSession $s2
    Check 'documentos-recuperados' ((@($docs.documents) | Where-Object { $_.title -eq 'Manual de prueba' }).Count -eq 1)
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    $failed++
    $results['error'] = $_.Exception.Message
} finally {
    if (-not $KeepArtifacts) {
        Write-Step 'Limpieza de lo creado por esta prueba'
        foreach ($c in @($srcName, $dstName)) { & docker rm -f $c *> $null }
        $own = & docker volume ls -q --filter "label=nexaro.test=$run"
        foreach ($v in $own) { if ($v -like 'nexaro-bkptest-*') { & docker volume rm $v *> $null } }
        if (Test-Path -LiteralPath (Join-Path $WorkDir $run)) {
            Set-TreeReadOnly (Join-Path $WorkDir $run) $false
            Remove-Item -LiteralPath (Join-Path $WorkDir $run) -Recurse -Force
        }
        Remove-Item -LiteralPath (Join-Path $WorkDir "$run-tampered") -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "Conservado: contenedores $srcName/$dstName, volúmenes $srcVolume/$dstVolume, copias en $backupRoot"
    }
}

Write-Host ''
$results.GetEnumerator() | ForEach-Object { Write-Host ("{0,-40} {1}" -f $_.Key, $_.Value) }
if ($failed -eq 0) { Write-Host 'PRUEBA DE RESTAURACIÓN: PASS'; exit 0 }
Write-Host "PRUEBA DE RESTAURACIÓN: FAIL ($failed)" -ForegroundColor Red
exit 1
