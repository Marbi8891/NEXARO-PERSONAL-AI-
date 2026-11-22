# ADR-0018: Documentos PDF con texto

- **Estado:** Aceptada
- **Fecha:** 2026-11-09

## Contexto

Los documentos solo admitían texto plano (ADR-0012). Las fuentes reales del usuario suelen ser PDF.

## Opciones

- A. Extraer el texto en el servidor con `pypdf`.
- B. Extraer en el navegador con pdf.js (archivos vendorizados, sin cambios de backend).
- C. Seguir solo con texto.

## Decisión

A. `POST /api/organizations/{id}/documents/pdf?title=&source=` recibe el PDF como cuerpo binario crudo
(`Content-Type: application/pdf`, sin `python-multipart`), extrae el texto en un hilo y lo guarda como
cualquier otro documento (mismos fragmentos, BM25, límites, deduplicación por hash del texto, auditoría y
permiso `documents:write`). Nueva dependencia fijada: `pypdf==7.0.0` (Python puro).

## Límites y riesgos

- Solo PDF con texto. Un escaneado devuelve 422 «no contiene texto»; no hay OCR.
- Tamaño del archivo: el global `MAX_BODY_BYTES` (2 MiB por defecto). Páginas: 300. Texto: 200.000
  caracteres, y la extracción se corta en cuanto se supera.
- pypdf procesa archivos no fiables: cualquier excepción del analizador se trata como «PDF no válido»,
  se rechazan los cifrados y el trabajo corre fuera del bucle de eventos. Un PDF patológico puede seguir
  consumiendo CPU en su hilo hasta terminar (no hay límite de tiempo); por eso solo suben quienes tienen
  `documents:write`. Vigilar avisos de seguridad de pypdf (`pip-audit` ya está en CI).
- Se pierde la estructura (tablas, columnas) y el orden de lectura puede alterarse.

## Consecuencias

- La imagen Docker incorpora `pypdf`; hay que reconstruirla.
- El PDF original no se conserva: solo el texto extraído.
