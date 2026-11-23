<#
.SYNOPSIS
  Acceso remoto PRIVADO a NEXARO con Tailscale Serve (docs/deployment/remote-access.md).

.DESCRIPTION
  check   (por defecto) Solo lee: Tailscale instalado y conectado, Serve/Funnel, puertos de
          NEXARO y Ollama, y configuración de orígenes y cookies. No cambia nada.
  plan    Muestra los comandos exactos que habría que ejecutar, sin ejecutarlos.
  enable  Publica http://127.0.0.1:8001 SOLO dentro de tu tailnet (Tailscale Serve, HTTPS).
          Exige -Apply. Nunca usa Funnel (Internet) y se niega si Funnel está activo.
  disable Retira la publicación de Serve. Exige -Apply.

  No instala Tailscale, no inicia sesión, no abre puertos del router ni toca Ollama.

.EXAMPLE
  pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\remote_access.ps1 check
.EXAMPLE
  pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\remote_access.ps1 enable -Apply
#>
[CmdletBinding()]
param(
    [ValidateSet('check', 'plan', 'enable', 'disable')]
    [string]$Action = 'check',
    [int]$LocalPort = 8001,
    [string]$Backend = 'nexaro-backend',
    [string]$OllamaContainers = 'ollama,nexaro-ollama',
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$problems = 0
function Ok([string]$m) { Write-Host "  OK    $m" }
function Warn([string]$m) { Write-Host "  AVISO $m" -ForegroundColor Yellow }
function Bad([string]$m) { Write-Host "  FALLO $m" -ForegroundColor Red; $script:problems++ }

function Get-Tailscale {
    $cmd = Get-Command tailscale -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $default = 'C:\Program Files\Tailscale\tailscale.exe'
    if (Test-Path -LiteralPath $default) { return $default }
    return $null
}

function Get-DnsName([string]$ts) {
    $status = & $ts status --json 2>$null | ConvertFrom-Json
    if ($null -eq $status -or $status.BackendState -ne 'Running') { return $null }
    return ($status.Self.DNSName).TrimEnd('.')
}

$ts = Get-Tailscale

if ($Action -eq 'check') {
    Write-Host '==> Tailscale'
    if (-not $ts) { Bad 'Tailscale no está instalado (instalación manual: docs/deployment/remote-access.md, paso 1)' } else {
        Ok "cliente: $ts"
        $dns = Get-DnsName $ts
        if (-not $dns) { Bad 'Tailscale no está conectado (tailscale up / iniciar sesión en la app)' } else {
            Ok "este equipo en la tailnet: $dns"
            $serve = (& $ts serve status 2>&1 | Out-String)
            if ($serve -match '(?i)funnel on|Funnel on') { Bad 'Tailscale FUNNEL está activo: NEXARO estaría en Internet. Desactívalo: tailscale funnel reset' }
            elseif ($serve -match "127\.0\.0\.1:$LocalPort|localhost:$LocalPort") { Ok "Serve publica 127.0.0.1:$LocalPort solo en la tailnet: https://$dns" }
            else { Warn 'Serve no publica NEXARO todavía (acción enable)' }
        }
    }

    Write-Host '==> Puertos de Docker'
    $ports = (& docker port $Backend 2>$null | Out-String).Trim()
    if (-not $ports) { Warn "$Backend no está en marcha o no publica puertos" }
    elseif ($ports -match '0\.0\.0\.0|\[::\]|:::') { Bad "$Backend publica en todas las interfaces: $ports" }
    else { Ok "$Backend solo en loopback: $($ports -replace "`r?`n", '; ')" }
    foreach ($o in $OllamaContainers.Split(',')) {
        $op = (& docker port $o.Trim() 2>$null | Out-String).Trim()
        if ($op) { Bad "Ollama ($o) publica puertos en el host: $op" } else { Ok "Ollama ($o) no publica puertos" }
    }

    Write-Host '==> Configuración del backend'
    $envJson = & docker inspect -f '{{json .Config.Env}}' $Backend 2>$null
    if ($envJson) {
        $envVars = $envJson | ConvertFrom-Json
        $origins = (($envVars | Where-Object { $_ -like 'ALLOWED_ORIGINS=*' }) -split '=', 2)[1]
        $secure = (($envVars | Where-Object { $_ -like 'COOKIE_SECURE=*' }) -split '=', 2)[1]
        if ($origins -match 'https://[^,]+\.ts\.net') { Ok "ALLOWED_ORIGINS incluye la URL de Tailscale" } else { Warn 'ALLOWED_ORIGINS no incluye https://<equipo>.<tailnet>.ts.net: el login remoto dará 403' }
        if ($secure -eq 'true') { Ok 'COOKIE_SECURE=true' } else { Warn 'COOKIE_SECURE no es true (recomendado al usar HTTPS de Tailscale)' }
    }
    Write-Host ''
    if ($problems -eq 0) { Write-Host 'Sin problemas bloqueantes.'; exit 0 }
    Write-Host "$problems problemas" -ForegroundColor Red
    exit 1
}

$dnsName = if ($ts) { Get-DnsName $ts } else { $null }
$url = if ($dnsName) { "https://$dnsName" } else { 'https://<equipo>.<tailnet>.ts.net' }
$serveCmd = "tailscale serve --bg --https=443 http://127.0.0.1:$LocalPort"

if ($Action -eq 'plan') {
    @"
1. (manual) Instala Tailscale para Windows desde https://tailscale.com/download e inicia sesión.
2. (manual) Instala Tailscale en Android (Google Play) con la MISMA cuenta.
3. En la consola de Tailscale: activa MagicDNS y HTTPS Certificates (DNS > HTTPS).
4. Publica NEXARO solo en la tailnet:
     $serveCmd
5. En C:\Users\pc\NEXARO-PERSONAL-AI-\.env:
     ALLOWED_ORIGINS=$url,http://127.0.0.1:$LocalPort,http://localhost:$LocalPort
     COOKIE_SECURE=true
   y recrea el backend:  docker compose -f C:\Users\pc\NEXARO-PERSONAL-AI-\compose.yaml up -d --no-deps backend
6. Comprueba:  pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\remote_access.ps1 check
7. Desde Android (Tailscale conectado): abre $url en Chrome > menú > Instalar aplicación.
"@ | Write-Host
    exit 0
}

if (-not $Apply) { throw "La acción '$Action' cambia la configuración de Tailscale: repítela con -Apply" }
if (-not $ts) { throw 'Tailscale no está instalado' }
if (-not $dnsName) { throw 'Tailscale no está conectado' }

if ($Action -eq 'enable') {
    $status = (& $ts serve status 2>&1 | Out-String)
    if ($status -match '(?i)funnel on') { throw 'Funnel está activo: desactívalo antes (tailscale funnel reset). NEXARO no se publica en Internet.' }
    & $ts serve --bg --https=443 "http://127.0.0.1:$LocalPort"
    if ($LASTEXITCODE -ne 0) { throw 'tailscale serve falló' }
    Write-Host "Publicado solo en tu tailnet: $url"
    Write-Host 'Recuerda añadir esa URL a ALLOWED_ORIGINS y COOKIE_SECURE=true (plan, paso 5).'
} elseif ($Action -eq 'disable') {
    & $ts serve --https=443 off
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo retirar la publicación' }
    Write-Host 'Publicación de Tailscale Serve retirada.'
}
