# NEXARO — Auditoría de línea base de ingeniería

Fecha: 2026-11-24
Base analizada: `main` en `65ecaea11a602aa1134c692322f5b9941a167322`
Alcance: inspección remota de workflows, estructura de tests, Makefile y auditorías/documentación existentes.
Limitación: no se ejecutaron tests ni comandos localmente. Los resultados de CI son estados remotos de GitHub.

## Resultado ejecutivo

La base es razonable para continuar como monolito modular. Hay una CI de calidad, seguridad, Terraform y Docker; una estructura de tests unitarios, integración, seguridad y frontend; y auditorías históricas con evidencias. Los siguientes cambios deben reforzar la reproducibilidad y evitar que los checks existentes den una falsa sensación de cobertura.

## Hallazgos

### NX-AUD-01 — No existe job Windows en CI
**Prioridad: P0 / alta para compatibilidad del proyecto.**

El workflow `.github/workflows/ci.yml` usa exclusivamente `ubuntu-latest`. El repositorio contiene scripts PowerShell para backup, verificación, restauración, tareas programadas y smoke tests, además de tests que dependen de PowerShell/Docker. No se valida la plataforma Windows en CI.

**Acción:** crear un job `windows-latest` con Python soportado, ejecutar lint/typecheck si son portables y la suite seleccionada de tests sin Docker. Los tests que requieran Docker deben identificarse explícitamente, no quedar mezclados con skips genéricos.

**Aceptación:** CI Windows estable; lista de tests omitidos y motivo visible; al menos tests de parsing/selección de imagen y scripts de backup bajo PowerShell 7.

### NX-AUD-02 — E2E de frontend existe, pero no está en el workflow CI
**Prioridad: P0 / media-alta.**

Hay un harness en `tests/frontend` (`browser.mjs`, `e2e.mjs`, `package.json`, `run.sh`), pero el workflow principal no lo invoca. El job Docker valida healthcheck y respuesta HTML, no el comportamiento de navegación ni los flujos principales de UI.

**Acción:** incorporar Chromium E2E como job independiente, con instalación reproducible y artifact limitado a logs/capturas sanitizadas si falla.

**Aceptación:** smoke E2E cubre carga, login/formulario de acceso y una navegación principal; no usa credenciales reales ni datos del usuario.

### NX-AUD-03 — Escaneo Terraform no bloquea por HIGH/CRITICAL
**Prioridad: P1.**

El job `terraform-scan` ejecuta Trivy config con `exit-code: "0"`; los hallazgos no bloquean CI. El comentario dice que es informativo en primera ejecución.

**Acción:** revisar el reporte actual y clasificar los findings; después establecer gate con `exit-code: "1"` para findings HIGH/CRITICAL, dejando excepciones documentadas y con expiración.

**Aceptación:** el job bloquea findings no aceptados; excepciones tienen ID, justificación, responsable y fecha de revisión.

### NX-AUD-04 — Revisión del alcance de pruebas y skips
**Prioridad: P1.**

El workflow usa cobertura con umbral de `pyproject.toml`, pero no se ha ejecutado una baseline independiente en este análisis. Los tests condicionados a herramientas externas pueden dar una señal incompleta si el skip no se comunica claramente.

**Acción:** registrar el resultado de la suite completa y categorizar tests: unitarios, integración, seguridad, frontend, Docker, Windows y dependientes de servicios. Auditar skips y markers.

**Aceptación:** artifact o resumen de CI informa total pass/fail/skip y los skips tienen una razón explícita; la baseline de cobertura queda registrada.

### NX-AUD-05 — Tests frontend y backend no se ejecutan como una matriz de responsabilidades
**Prioridad: P1.**

Los jobs actuales concentran backend en `quality`; frontend está cubierto por análisis estático indirecto y Docker smoke. El harness E2E existe, pero está separado de CI.

**Acción:** separar claramente `backend-quality`, `frontend-e2e`, `security`, `docker-smoke` y `terraform`, manteniendo dependencias mínimas y cancelación de runs redundantes.

**Aceptación:** los jobs pueden ejecutarse independientemente para diagnóstico; PRs reciben feedback rápido antes de gates más pesados.

## Elementos confirmados que ya existen

- Ruff lint y format check.
- mypy.
- Pytest con cobertura.
- pip-audit para dependencias declaradas.
- Bandit.
- Gitleaks con historial del checkout probado.
- SBOM CycloneDX como artifact.
- Terraform fmt/validate por dev, staging y prod.
- Trivy config para Terraform, actualmente informativo.
- Build Docker, escaneo HIGH/CRITICAL con parche disponible y smoke healthcheck.
- Tests separados en unit, integration, security y frontend.
- E2E frontend basado en navegador en el repositorio, sin job de CI visible.

## Próxima ejecución recomendada

1. Obtener baseline real del último CI de `main` tras el merge del PR #26.
2. Añadir job Windows de forma incremental.
3. Conectar harness frontend al CI.
4. Revisar y convertir Terraform scan en gate.
5. Hacer revisión endpoint-permission/ownership antes de comenzar Agent Runtime.

## No se ha hecho

- No se han ejecutado tests localmente.
- No se han cambiado código de aplicación, dependencias, Docker, infraestructura ni datos.
- No se han creado recursos cloud ni desplegado.
- Este documento es una auditoría estática basada en los archivos remotos citados y no sustituye un pentest.
