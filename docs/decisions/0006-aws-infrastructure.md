# ADR-0006: Infraestructura AWS como Terraform por entorno, sin desplegar la app todavía

- **Estado:** Propuesta implementada como código; **no aplicada** (ningún recurso AWS creado)
- **Fecha:** 2026-11-09

## Contexto
Se pide dejar AWS preparado como IaC para dev, staging y prod, con mínimo privilegio y costes
documentados, sin crear recursos reales sin autorización expresa. Dos hechos condicionan el diseño:
la aplicación solo ejecuta sobre SQLite en un volumen (ADR-0005) y el disco de Fargate es efímero.

## Opciones
- **A. Todos los servicios de la lista desde el principio** (SQS, EventBridge, Step Functions,
  ElastiCache, CloudFront, WAF, Backup...). Sin consumidor en el código: coste fijo y superficie
  sin valor.
- **B. Solo lo que el código usa o usará de inmediato**, modular, con interruptores, y una lista
  explícita de lo diferido con su disparador.
- **C. Un solo servidor (EC2/Lightsail) con Docker Compose.** Más barato, pero no es el objetivo.

## Decisión
**B.** Un módulo `stack` compone `network`, `kms`, `ecr`, `storage`, `app` (ALB + ECS Fargate +
IAM), `database` (Aurora PostgreSQL Serverless v2, apagada), `observability` (alarmas SNS +
AWS Budgets) y `security_baseline` (GuardDuty, CloudTrail). Cada entorno es un directorio fino que
fija valores.

- `desired_count = 0` y `enable_database = false` en todos los entornos hasta que la aplicación
  ejecute sobre PostgreSQL. Desplegarla antes perdería datos en cada reinicio.
- HTTPS obligatorio (certificado ACM como variable obligatoria): la app exige cookies `Secure`.
- Rol de la tarea sin comodines: S3 solo sobre el bucket de documentos, Bedrock y SageMaker solo
  sobre ARNs explícitos (lista vacía = sin acceso). Los comodines de claves KMS y políticas Deny
  llevan la marca `allow-wildcard` y un test los exige justificados.
- La contraseña maestra de Aurora la gestiona AWS (`manage_master_user_password`): no pasa por el
  estado ni por el repositorio.
- Una sola NAT Gateway (no una por zona): un fallo de zona corta la salida a Internet de las
  tareas privadas. Se asume por coste; revisar en producción real.
- El estado remoto (bucket S3 con bloqueo por fichero) se crea a mano, una vez, con autorización.

## Diferido (con disparador)
| Servicio | Disparador |
|---|---|
| SQS, EventBridge, Step Functions | Primer flujo asíncrono real (ingesta de documentos, automatizaciones) |
| ElastiCache | Medición de que la base de datos o las sesiones son el cuello de botella |
| CloudFront, WAF | Exposición pública con tráfico real o requisito de cumplimiento |
| AWS Backup | Necesidad de retención más allá de las copias automáticas de Aurora (14 días en prod) |
| SageMaker (endpoint) | Un modelo propio que justifique pagar un endpoint; el permiso de invocación ya existe |

## Validación y límites
- Aquí solo se pudo ejecutar `tofu fmt` y tests estáticos propios (cableado entre módulos,
  comodines, secretos, cifrado, HTTPS). **No se ejecutó `terraform validate` ni `plan`**: el
  registro de proveedores no es accesible desde el entorno de desarrollo. El CI ejecuta `validate`
  por entorno; hasta que pase, la infraestructura no está validada.
- Nombres de atributos y versiones (provider `~> 5.70`, Aurora `16.4`, política TLS del ALB) están
  escritos de memoria: VERIFY en el primer `init`/`validate`.
- La disponibilidad de Bedrock y de cada modelo en la región es UNKNOWN; el acceso al modelo se
  solicita en la consola de AWS, fuera de Terraform.
- Sin VPC Flow Logs, sin endpoints VPC y sin ARM64: se añadirán cuando haya medidas que lo justifiquen.

## Consecuencias
Aplicar el código no despliega la aplicación (0 tareas), pero sí crea recursos con coste fijo
(ALB, NAT en staging/prod, claves KMS). Ver `docs/deployment/aws-costs.md`.
