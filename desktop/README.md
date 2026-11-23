# NEXARO AI — aplicación de escritorio para Windows

Envoltorio Electron que arranca y vigila la infraestructura de NEXARO (Docker Compose, Ollama,
backend) y abre el frontend existente en una ventana nativa. No modifica el backend ni el frontend.

```bash
npm install && npm start   # desarrollo
npm test                   # 81 tests
npm run dist:win           # instalador .exe (en Windows)
```

| Documento | Para |
|---|---|
| [DESKTOP_IMPLEMENTATION_PLAN.md](DESKTOP_IMPLEMENTATION_PLAN.md) | Auditoría, arquitectura propuesta, riesgos y fases |
| [DESKTOP_ARCHITECTURE.md](DESKTOP_ARCHITECTURE.md) | Cómo está hecho |
| [WINDOWS_DESKTOP_GUIDE.md](WINDOWS_DESKTOP_GUIDE.md) | Desarrollar, probar y generar el instalador |
| [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md) | Instalar, actualizar y desinstalar |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Errores y recuperación |
| [docs/TESTING.md](docs/TESTING.md) | Qué se probó y qué falta probar en Windows |

Estado: **hito 1** (núcleo de arranque, servicios, seguridad, instalador configurado). Bandeja,
ajustes, gestión de modelos, asistente y diagnóstico exportable son los hitos 2–6.
