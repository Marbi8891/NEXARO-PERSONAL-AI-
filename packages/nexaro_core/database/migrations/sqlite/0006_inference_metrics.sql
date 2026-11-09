-- Métricas de inferencia por petición (ADR-0014). Ver postgresql/0006_inference_metrics.sql.
-- Milisegundos. NULL = el proveedor no lo informa (Bedrock/SageMaker) o la petición no llegó a generar.
ALTER TABLE model_usage ADD COLUMN ttft_ms REAL;
ALTER TABLE model_usage ADD COLUMN load_ms REAL;
ALTER TABLE model_usage ADD COLUMN prompt_eval_ms REAL;
ALTER TABLE model_usage ADD COLUMN generation_ms REAL;
