#!/usr/bin/env bash
# Retención de copias de seguridad: conserva las N más recientes de nexaro.pre-rebuild-*.db y NO toca
# nunca nexaro-pre-auth-migration-*.db ni ningún otro fichero. Por defecto solo muestra qué borraría.
# Uso: scripts/prune_backups.sh [--keep N] [--dir backups] [--apply]
set -euo pipefail

keep=10
dir="backups"
apply=0
while [ $# -gt 0 ]; do
  case "$1" in
    --keep) keep="$2"; shift 2 ;;
    --dir) dir="$2"; shift 2 ;;
    --apply) apply=1; shift ;;
    *) echo "uso: $0 [--keep N] [--dir DIR] [--apply]" >&2; exit 2 ;;
  esac
done
case "$keep" in ''|*[!0-9]*) echo "--keep debe ser un entero" >&2; exit 2 ;; esac
[ "$keep" -ge 1 ] || { echo "--keep debe ser >= 1" >&2; exit 2; }
[ -d "$dir" ] || { echo "no existe el directorio $dir" >&2; exit 2; }

# Los nombres llevan sello de fecha: el orden alfabético es el cronológico.
mapfile -t all < <(find "$dir" -maxdepth 1 -type f -name 'nexaro.pre-rebuild-*.db' | sort)
total=${#all[@]}
if [ "$total" -le "$keep" ]; then
  echo "Hay $total copias (límite $keep): nada que podar."
  exit 0
fi

remove=$((total - keep))
for file in "${all[@]:0:$remove}"; do
  if [ "$apply" -eq 1 ]; then
    rm -- "$file"
    echo "borrada: $file"
  else
    echo "se borraría: $file"
  fi
done
[ "$apply" -eq 1 ] || echo "(simulación; añade --apply para borrar)"
