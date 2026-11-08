# Costes de AWS (orden de magnitud)

> **VERIFY.** Precios de lista aproximados (región de la UE, USD), escritos de memoria y sin
> consultar AWS. Úsalos para comparar entornos, no como presupuesto. Calcula el real con la
> AWS Pricing Calculator antes de aplicar nada.

## Costes fijos (existen aunque no haya tráfico)

| Recurso | Aprox./mes | Lo controla |
|---|---|---|
| Application Load Balancer | ~16-20 $ | siempre presente en cada entorno; `terraform destroy` si no se usa |
| NAT Gateway | ~33 $ + 0,045 $/GB | `enable_nat` (dev: desactivado) |
| Claves KMS | 1 $ por clave | una por entorno |
| Aurora Serverless v2 | ~45 $ por 0,5 ACU continuo + almacenamiento | `enable_database` (desactivado en todos) |
| Fargate 0,5 vCPU / 1 GB | ~18 $ por tarea 24/7 | `desired_count` (0 en todos) |
| GuardDuty / CloudTrail | por uso (eventos analizados / almacenamiento) | `enable_guardduty`, `enable_cloudtrail` |
| CloudWatch Logs | ~0,5 $/GB ingerido | `log_retention_days` |
| Secrets Manager (contraseña de Aurora) | ~0,4 $/secreto | solo con base de datos |

## Variables (por uso)
- **Bedrock**: por token y por modelo. UNKNOWN hasta elegir modelo. El gateway aplica un
  presupuesto mensual propio (`AI_CLOUD_MONTHLY_BUDGET_USD`) y AWS Budgets avisa por separado.
- Transferencia de datos, S3, solicitudes de ECR: normalmente marginales a este tamaño.

## Estimación por entorno tal como está el código (aplicado, app sin desplegar)

| Entorno | Qué existe | Orden de magnitud |
|---|---|---|
| dev | ALB, KMS, ECR, S3, alarmas | ~20 $/mes |
| staging | + NAT, GuardDuty | ~60-70 $/mes |
| prod | + NAT, GuardDuty, CloudTrail | ~65-80 $/mes |

Al desplegar la aplicación con PostgreSQL, suma tareas (~18 $ cada una) y Aurora (~45 $ con 0,5 ACU
en staging; más en prod según `database_min_acu`).

## Control del gasto
- AWS Budgets avisa al 80 % real y al 100 % previsto. **Avisa, no corta.**
- Para cortar de verdad hay que parar recursos (`desired_count = 0`, `terraform destroy`).
