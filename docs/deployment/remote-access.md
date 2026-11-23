# Acceso remoto privado (Tailscale)

Objetivo: usar NEXARO desde el Android, el ThinkPad y el MacBook **sin** abrir puertos del router,
sin publicar el backend en Internet y sin exponer Ollama ni SQLite.

**Estado: preparado, NO activado.** Tailscale no está instalado en el ThinkPad (comprobado con
`scripts/remote_access.ps1 check`). Instalarlo, iniciar sesión y publicar con Serve cambian el
sistema y la red: los pasos marcados «(tú)» requieren tu autorización y los haces tú.

## Diseño

```
Android / MacBook ──(WireGuard, solo dispositivos de tu tailnet)──► ThinkPad
                                                                   tailscale serve :443 (HTTPS)
                                                                        │ proxy local
                                                                        ▼
                                                     127.0.0.1:8001 → contenedor nexaro-backend
                                                                        │ red Docker interna
                                                                        ▼
                                                              ollama (sin puertos publicados)
```

- **Tailscale Serve** (no Funnel): la URL `https://<thinkpad>.<tailnet>.ts.net` solo resuelve y
  responde dentro de tu tailnet. Certificado HTTPS válido emitido por Tailscale (Let's Encrypt).
- El backend sigue publicado **solo en 127.0.0.1:8001**: Serve hace de proxy local. No hace falta
  `0.0.0.0` ni reglas de firewall de entrada.
- Ollama no publica puertos (el script lo comprueba). SQLite vive en un volumen Docker sin acceso de red.
- La autenticación de NEXARO sigue igual (sesión, Origin, límites). Tailscale añade una capa: solo
  dispositivos autenticados en tu cuenta llegan a la URL.
- **Funnel está prohibido**: publicaría NEXARO en Internet. `remote_access.ps1` nunca lo usa y se
  niega a activar Serve si detecta Funnel.

Alternativas descartadas: abrir el puerto en el router (exposición pública), `0.0.0.0` en la LAN
(sin TLS, cualquiera de la wifi llega al login), túneles públicos (Cloudflare Tunnel, ngrok: el
servicio quedaría en Internet).

## Activación (cuando lo autorices)

1. **(tú)** Instala Tailscale para Windows desde https://tailscale.com/download/windows e inicia
   sesión. Instala Tailscale en Android (Google Play) y, si quieres, en el MacBook, **con la misma
   cuenta**.
2. **(tú)** En https://login.tailscale.com/admin/dns: activa **MagicDNS** y **HTTPS Certificates**.
3. Comprueba el estado (solo lectura):

   ```powershell
   pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\remote_access.ps1 check
   ```

4. Muestra los comandos exactos con tu nombre de equipo:

   ```powershell
   pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\remote_access.ps1 plan
   ```

5. **(tú)** Publica NEXARO solo en la tailnet:

   ```powershell
   pwsh -File C:\Users\pc\NEXARO-PERSONAL-AI-\scripts\remote_access.ps1 enable -Apply
   ```

   Equivale a `tailscale serve --bg --https=443 http://127.0.0.1:8001`.
6. **(tú)** En `C:\Users\pc\NEXARO-PERSONAL-AI-\.env` (no se versiona), con tu URL real:

   ```
   ALLOWED_ORIGINS=https://thinkpad.tu-tailnet.ts.net,http://127.0.0.1:8001,http://localhost:8001
   COOKIE_SECURE=true
   ```

   y recrea solo el backend (los datos están en el volumen; no se pierden):

   ```powershell
   docker compose -f C:\Users\pc\NEXARO-PERSONAL-AI-\compose.yaml up -d --no-deps backend
   ```

   Con `COOKIE_SECURE=true` la cookie solo viaja por HTTPS: usa también la URL de Tailscale en el
   propio ThinkPad (Chrome/Edge aceptan cookies `Secure` en `http://localhost`, pero no en otras IPs).
7. Vuelve a ejecutar `check`: debe terminar en «Sin problemas bloqueantes».

Para retirarlo: `remote_access.ps1 disable -Apply`.

## Android

1. Abre la app Tailscale y conéctate (interruptor activo).
2. En Chrome abre `https://<thinkpad>.<tailnet>.ts.net` e inicia sesión en NEXARO.
3. Menú ⋮ → **Instalar aplicación** (o «Añadir a pantalla de inicio»). Queda como PWA a pantalla
   completa. El service worker solo funciona en HTTPS; por eso se usa la URL de Tailscale y no la IP.
4. Si la URL no carga: comprueba que Tailscale está conectado en el móvil, que el ThinkPad está
   encendido, Docker Desktop arrancado y `nexaro-backend` sano.

## Seguridad

| Control | Cómo |
|---|---|
| Solo tus dispositivos | Cuenta de Tailscale propia; revisa **Machines** y elimina los que no reconozcas. Opcional: ACL que solo permita el puerto 443 del ThinkPad a tus dispositivos |
| Sin Internet | Serve, nunca Funnel; el script lo verifica |
| Backend no expuesto | `127.0.0.1:8001` (verificado por `check` y por `tests/unit/test_container_hardening.py`) |
| Ollama no expuesto | Sin `ports:` (verificado por `check` y tests) |
| Cookies | `COOKIE_SECURE=true`, `HttpOnly`, `SameSite=Strict` |
| CSRF | El backend exige `Origin` en `ALLOWED_ORIGINS` para cualquier escritura |
| Fuerza bruta | 5 intentos por cuenta / 15 min. Detrás de Serve todos los clientes llegan como 127.0.0.1, así que el límite por IP (`LOGIN_IP_MAX_ATTEMPTS=50`) es global; el límite por cuenta sigue siendo individual |
| Dispositivo perdido | Elimínalo en la consola de Tailscale y cambia tu contraseña en NEXARO (Perfil → Contraseña: cierra las demás sesiones) |

## Arranque tras reiniciar Windows

Docker Desktop arranca al iniciar sesión en Windows si tienes activado *Settings → General → Start
Docker Desktop when you sign in*; los contenedores con `restart: unless-stopped` se levantan solos.
Tailscale para Windows se ejecuta como servicio y conserva la configuración de Serve. Hasta que no
inicias sesión en Windows, Docker Desktop no arranca: el acceso remoto no estará disponible tras un
reinicio sin sesión iniciada.
