# Modelo de amenazas

## Activos

| Activo | Dónde | Confidencialidad |
|---|---|---|
| Conversaciones y documentos | SQLite `/data/nexaro.db` | Alta |
| Hash de contraseñas, sesiones, claves de API (hash) | SQLite | Alta |
| Gastos de organizaciones | SQLite | Alta |
| Disponibilidad del modelo local | Ollama (CPU) | Media |
| Copias de seguridad | `backups/` en el host | Alta (contienen lo mismo que la base) |
| Auditoría | tabla `audit_events` (append-only) | Media |

## Fronteras de confianza

1. Navegador ↔ backend: no se confía en nada que llegue (validación Pydantic, `Origin`, sesión, permisos).
2. Backend ↔ Ollama: red Docker; Ollama **no autentica**. Se confía en que no es accesible desde fuera (VERIFY-01).
3. Contenido de documentos y salida del modelo: **datos no confiables**. Nunca se ejecutan ni se interpretan como instrucciones del sistema.
4. Host ↔ contenedor: volumen `nexaro_data` (escritura) y `./frontend` (solo lectura).

## Amenazas y controles

| Amenaza | Control | Prueba |
|---|---|---|
| Acceso sin sesión | `CurrentUser`/`AdminUser`/`require_permission`; 401/403/404 | `tests/security/test_access_control.py` |
| IDOR/BOLA entre usuarios y organizaciones | Consultas siempre acotadas por usuario u organización; FK compuestas; RLS | `test_access_control.py`, `test_tenant_isolation.py`, `test_llm_security.py` |
| CSRF | `SameSite=Strict` + `Origin` obligatorio | `test_auth_flow.py`, `test_access_control.py` |
| Fuerza bruta de login | Bloqueo por cuenta (5/15 min) y por IP (umbral configurable) | `test_access_control.py`, `test_abuse_limits.py` |
| Agotar la CPU del modelo | 30 peticiones/min por usuario, 2 generaciones simultáneas, topes de tokens, historial y entrada | `test_abuse_limits.py` |
| Cuerpos enormes | Límite de 2 MiB (413) antes de leer | `test_abuse_limits.py` |
| XSS (almacenado, reflejado, DOM) | Sin `innerHTML`; Markdown propio con nodos DOM; CSP estricta | `test_frontend_policy.py`, E2E |
| Inyección SQL | Parámetros `?`; f-strings solo con huecos fijos | `test_sql_injection.py` |
| Inyección de prompt directa | Mensaje de sistema único del backend; el usuario nunca fija el rol | `test_llm_security.py` |
| Inyección indirecta por documentos | Delimitadores neutralizados; el contexto viaja como mensaje de usuario y el prompt dice que es contenido | `test_llm_security.py` |
| Fuga entre usuarios por el modelo | Cada petición solo lleva el historial de su conversación | `test_llm_security.py` |
| Fuga del prompt del sistema | Ningún endpoint lo devuelve. **El modelo podría repetirlo si se le pide: el prompt no contiene secretos** | `test_llm_security.py` |
| Secretos en logs | Redacción de claves sensibles; no se registra contenido, consultas ni cabeceras | `test_logging.py` |
| Falsificar líneas de log | JSON: los saltos de línea se escapan | `test_logging.py` |
| Escape del contenedor / abuso de privilegios | Usuario no root, `cap_drop: ALL`, `no-new-privileges`, `read_only`, límites | `test_container_hardening.py` (estático) |
| SSRF | No hay URLs de usuario; solo `OLLAMA_BASE_URL` (configuración) | — (no aplica hoy) |

## Fuera de alcance / no cubierto

- Open WebUI, Supabase y el propio Ollama.
- Un atacante con acceso al host o a la sesión de macOS (lee la base y las copias; ver cifrado en reposo).
- Agentes y herramientas: **no existen**. Cuando se añadan: permisos mínimos por herramienta, aprobación humana para acciones sensibles, registro de cada ejecución y validación de las salidas del modelo antes de actuar. No hay que fiarse del prompt del sistema como barrera.
- Denegación de servicio distribuida: no hay balanceador ni WAF; el servicio está en `127.0.0.1`.
