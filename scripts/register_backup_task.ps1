<#
.SYNOPSIS
  Programa la copia diaria de NEXARO en el Programador de tareas de Windows.

.DESCRIPTION
  Por defecto SOLO muestra lo que haría (no cambia el sistema). Con -Register crea o actualiza la
  tarea "NEXARO Backup diario" para el usuario actual (sin privilegios elevados), que ejecuta
  backup_nexaro.ps1 -Reason daily a la hora indicada y, si el equipo estaba apagado, en cuanto
  vuelva a estar disponible. Modificar el Programador de tareas es un cambio del sistema operativo:
  ejecútalo tú cuando lo apruebes (BACKUP_RESTORE.md).

.EXAMPLE
  pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\register_backup_task.ps1              # simulación
.EXAMPLE
  pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\register_backup_task.ps1 -Register -At 03:30
#>
[CmdletBinding()]
param(
    [string]$At = '03:30',
    [string]$BackupRoot = (Join-Path $env:USERPROFILE 'NEXARO-Backups'),
    [int]$Keep = 14,
    [string]$TaskName = 'NEXARO Backup diario',
    [switch]$Register
)

$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'backup_nexaro.ps1'
$shell = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
if (-not $shell) { $shell = (Get-Command powershell).Source }
$arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$script`" -Reason daily -Keep $Keep -BackupRoot `"$BackupRoot`""

Write-Host "Tarea:      $TaskName"
Write-Host "Cuándo:     cada día a las $At (y al volver a estar disponible si se perdió)"
Write-Host "Programa:   $shell"
Write-Host "Argumentos: $arguments"

if (-not $Register) {
    Write-Host ''
    Write-Host 'Simulación: no se ha cambiado nada. Añade -Register para crear la tarea.'
    exit 0
}

$action = New-ScheduledTaskAction -Execute $shell -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description 'Copia verificada de NEXARO (scripts/backup_nexaro.ps1)' -Force | Out-Null
Write-Host "Tarea '$TaskName' registrada. Pruébala con: Start-ScheduledTask -TaskName '$TaskName'"
