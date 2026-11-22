-- Métricas de inferencia por petición (ADR-0014). Mismas columnas que sqlite/0006_inference_metrics.sql.
ALTER TABLE model_usage ADD COLUMN ttft_ms double precision;
ALTER TABLE model_usage ADD COLUMN load_ms double precision;
ALTER TABLE model_usage ADD COLUMN prompt_eval_ms double precision;
ALTER TABLE model_usage ADD COLUMN generation_ms double precision;
