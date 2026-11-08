# Despliegue

## Local (Docker)

```bash
docker compose up -d --build backend
```

Volumen persistente `nexaro-personal-ai_nexaro_data` (SQLite en `/data/nexaro.db`), puerto
`127.0.0.1:8001`, red externa `ollama-local_default`.

### Reconstruir conservando datos

`scripts/rebuild_backend.sh [--yes]` verifica la copia de seguridad, ejecuta los tests, hace
una copia fresca de la base viva, etiqueta la imagen anterior como `rollback-<fecha>`,
reconstruye solo `backend` y comprueba el resultado. Necesita un entorno Python con
`requirements/dev.txt` (variable `PYTHON`).

### Primer administrador

```bash
docker exec -it nexaro-backend python -m nexaro_api.bootstrap_admin \
    --confirm-database /data/nexaro.db --email TU_CORREO [--promote-existing]
```

## Producción / AWS

**No implementado.** Está previsto describirlo como Terraform por entorno (dev/staging/prod)
con mínimo privilegio y costes documentados, sin crearlo sin autorización expresa.
Con `NEXARO_ENV=production` la aplicación exige `COOKIE_SECURE=true` y orígenes https.
