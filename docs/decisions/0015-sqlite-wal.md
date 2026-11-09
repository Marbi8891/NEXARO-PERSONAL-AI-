# ADR-0015: SQLite en modo WAL

- **Estado:** Aceptada
- **Fecha:** 2026-11-09

## Contexto

Cada operación abre su propia conexión SQLite. Con el diario por defecto, una escritura (p. ej. el
guardado al terminar una respuesta en streaming) bloquea a los lectores y viceversa; el tiempo de
espera era el de por defecto de Python (5 s). Impacto real sin medir.

## Opciones

- A. Dejar el diario por defecto.
- B. WAL + `synchronous=NORMAL` + espera de bloqueos de 10 s en `Database.connect()`.
- C. Migrar a PostgreSQL ya (ADR-0005 lo deja para cuando haya necesidad real).

## Decisión

B. El modo WAL se guarda en el fichero; repetir el PRAGMA en cada conexión es barato.

## Razón y trade-offs

Lectores y un escritor dejan de bloquearse. A cambio: aparecen `nexaro.db-wal` y `-shm` junto a la base
(están en el volumen), una copia solo del `.db` puede perder datos recientes y WAL no es apto para
sistemas de ficheros de red. `synchronous=NORMAL` en WAL puede perder las últimas transacciones ante un
corte de energía del equipo (no corrompe la base); con un fallo del proceso no se pierde nada.

## Consecuencias

- Las copias de seguridad deben usar la API de backup de SQLite (`scripts/rebuild_backend.sh` ya lo hace) o copiar `-wal` y `-shm` con el servicio parado.
- Si algún día hay más de una instancia, la solución es PostgreSQL, no más SQLite.
