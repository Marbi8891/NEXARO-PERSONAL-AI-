# Contribuir

1. Rama desde `main`; cambios pequeños y verificables.
2. `make check` en verde (ruff, mypy, pytest con cobertura).
3. Decisiones de arquitectura relevantes: un ADR en `docs/decisions` (estado, contexto,
   opciones, decisión, razón, trade-offs, consecuencias, fecha).
4. Respeta las reglas de dependencia de `ARCHITECTURE.md`; las comprueba un test.
5. Nada de secretos, bases de datos ni copias de seguridad en commits.
6. Commits con prefijo (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `security:`).
