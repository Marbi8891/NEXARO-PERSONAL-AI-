# ADR-0004: AI Gateway con políticas, respaldo y registro de uso

- **Estado:** Aceptada (implementada y probada con dobles; Bedrock/SageMaker sin probar contra AWS real)
- **Fecha:** 2026-11-08

## Contexto
Los productos deben poder usar modelos locales (Ollama) y, en el futuro, de AWS sin conocer al
proveedor. Hay que limitar entrada/salida, controlar coste y evitar que datos salgan a la nube
por accidente.

## Opciones
- **A. Cada producto llama a su proveedor.** Sin capa; duplica límites, reintentos y registro.
- **B. Gateway único que implementa el contrato `ChatProvider`.** Políticas en un sitio.
- **C. Proxy tipo LiteLLM como servicio aparte.** Más funciones, otro componente que operar.

## Decisión
**B.** `Gateway` expone el mismo contrato que un proveedor, así los casos de uso no cambian.
Rutas ordenadas (`AI_PROVIDER_ORDER`) con respaldo. Política: tope de entrada y salida, timeout,
reintentos solo ante indisponibilidad, nube desactivada por defecto, presupuesto mensual para
proveedores de pago. Cada intento se registra en `model_usage` sin contenido de mensajes.

## Razón
Es la capa mínima que concentra las reglas sin añadir un servicio. C se reconsidera si hacen
falta decenas de proveedores.

## Trade-offs y límites
- El presupuesto se comprueba antes de llamar: peticiones concurrentes pueden pasarse un poco.
- El coste usa el precio configurado a mano; si el proveedor no devuelve tokens, el coste es
  desconocido (NULL) y no cuenta. SageMaker no tiene precio por token: su control real será
  AWS Budgets (fase Terraform).
- botocore no admite timeout por llamada: se fija al crear el cliente.
- `health()` de Bedrock/SageMaker solo valida configuración (una llamada real costaría dinero).
- SageMaker asume una API estilo OpenAI Chat (TGI/vLLM): **VERIFY** contra el endpoint real.
- La configuración por organización queda para la fase multiorganización.

## Consecuencias
Activar la nube exige a la vez `AI_ALLOW_CLOUD`, presupuesto, región y precios; si falta algo la
aplicación no arranca. El gateway nunca salta a la nube como respaldo si la política la prohíbe.
