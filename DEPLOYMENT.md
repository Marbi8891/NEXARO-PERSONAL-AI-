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

### Nube (opcional, desactivada)

`docker build --build-arg INSTALL_AWS=1 .` instala boto3. Variables en `.env.example`. Las
credenciales vienen del rol/entorno de AWS, no del repositorio. Mientras `AI_ALLOW_CLOUD` no sea
`true`, ningún dato sale a la nube.

## AWS (Terraform, sin aplicar)

Código en `infrastructure/aws/terraform` (módulos + `envs/{dev,staging,prod}`). **No se ha creado
ningún recurso.** Decisiones y límites: [ADR-0006](docs/decisions/0006-aws-infrastructure.md);
costes: [docs/deployment/aws-costs.md](docs/deployment/aws-costs.md).

Para aplicarlo (con tu autorización expresa, desde tu máquina):

1. Crea una vez el bucket de estado (cifrado, con versionado) y copia `backend.hcl.example` a
   `backend.hcl` en el entorno.
2. Copia `terraform.tfvars.example` a `terraform.tfvars` (ignorado por git).
3. `terraform init -backend-config=backend.hcl && terraform validate && terraform plan`.
   Revisa el plan antes de `apply`. **VERIFY**: el código no se ha validado contra el proveedor.
4. Sube la imagen a ECR con una etiqueta inmutable y fija `image_tag`.

La aplicación **no debe desplegarse** (`desired_count` > 0) hasta que ejecute sobre PostgreSQL
(ADR-0005): con SQLite el disco de Fargate se pierde en cada reinicio. Con `NEXARO_ENV=production`
la aplicación exige `COOKIE_SECURE=true` y orígenes https.
