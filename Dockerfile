# Imagen fijada por digest (misma que se construyó y probó). Política de actualización: cada mes, o
# ante un aviso de seguridad, tomar la nueva con `docker pull python:3.12-slim`, copiar su digest
# aquí, pasar los tests y reconstruir con scripts/rebuild_backend.sh.
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/packages:/app/apps/api

RUN groupadd --gid 10001 nexaro \
    && useradd --uid 10001 --gid nexaro --create-home nexaro

# boto3 (~70 MB) solo si se van a usar Bedrock/SageMaker: docker build --build-arg INSTALL_AWS=1
ARG INSTALL_AWS=0
COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/base.txt \
    && if [ "$INSTALL_AWS" = "1" ]; then pip install --no-cache-dir -r requirements/aws.txt; fi

COPY packages ./packages
COPY products ./products
COPY apps/api ./apps/api
# La imagen es autosuficiente: en desarrollo, compose.yaml la sustituye por un bind mount de solo lectura.
COPY frontend ./frontend

# El contenedor corre como uid 10001: el código debe ser legible aunque en el host tenga permisos 600.
RUN chmod -R a+rX /app

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health/live', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "nexaro_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
