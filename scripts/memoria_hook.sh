#!/usr/bin/env bash
# Envoltorio de los hooks de memoria: resuelve el intérprete y delega.
#
# Se localiza a sí mismo desde BASH_SOURCE en vez de depender del directorio de
# trabajo: un hook puede ejecutarse desde cualquier cwd y la memoria no debe
# dejar de funcionar por eso.
#
# Sale SIEMPRE con 0. Un código distinto puede cortar el turno del usuario y la
# memoria es auxiliar (etapa 7G del plan). Si no hay intérprete utilizable, el
# evento simplemente no se recuerda.
set +e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"
[ -n "$DIR" ] || exit 0
HOOK="$DIR/scripts/memoria_hook.py"
[ -f "$HOOK" ] || exit 0

# El camino del hook solo necesita la biblioteca estándar (sqlite3) y el paquete
# propio: ni ChromaDB ni el modelo de embeddings. Por eso cualquier Python 3.10+
# sirve y el venv es preferencia, no requisito.
for P in "$DIR/venv/Scripts/python.exe" "$DIR/venv/bin/python"; do
  if [ -x "$P" ]; then exec "$P" "$HOOK" "$@"; fi
done
if command -v python3 >/dev/null 2>&1; then exec python3 "$HOOK" "$@"; fi
if command -v python  >/dev/null 2>&1; then exec python  "$HOOK" "$@"; fi
exit 0
