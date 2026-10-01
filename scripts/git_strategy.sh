#!/usr/bin/env bash
# git_strategy.sh — disciplina de ramas para la regla absoluta 4 de CLAUDE.md.
#
# Nunca commitea en main, nunca usa --force, --no-verify ni `git add -A`, y no inventa
# mensajes de commit: quien lo invoca declara el mensaje y las rutas exactas.
#
# Uso (en Windows, desde Git Bash: en PowerShell `bash` puede resolver a WSL):
#   bash scripts/git_strategy.sh 0 <fix|feat>/<slug>
#       crea la rama o cambia a ella (arrastra el WIP sin commitear)
#   bash scripts/git_strategy.sh 1 -m "<mensaje>" [-m "<párrafo>"]... -- <ruta>...
#       commit SOLO de las rutas declaradas, tras verificar la política de datos
#   bash scripts/git_strategy.sh 2
#       push de la rama actual a origin
#   bash scripts/git_strategy.sh 3 [--confirmar <rama>] [-m "<párrafo>"]...
#       gates locales + merge --no-ff de la rama actual a main; pide escribir el nombre
#       de la rama en una terminal, o --confirmar <rama> cuando lo ordena el operador.
#       El push de main y run_regression.py (requiere corpus) siguen siendo manuales.
#
# Compatibilidad: en el paso 0 la rama puede venir de ITOS_BRANCH si no se pasa argumento.
# Rama principal configurable con ITOS_MAIN (default: main); intérprete con PYTHON.
set -euo pipefail

MAIN="${ITOS_MAIN:-main}"
RAMA_RE='^(fix|feat)/[a-z0-9][a-z0-9._-]*$'

die() { echo "❌ $*" >&2; exit 1; }

cd "$(git rev-parse --show-toplevel)"

rama_actual() { git branch --show-current; }

validar_rama() {
  [[ "$1" =~ $RAMA_RE ]] || die "Rama inválida: '$1'. Usa fix/<slug> o feat/<slug> (minúsculas, dígitos, '.', '_' o '-')."
}

dentro_de_rutas() {  # dentro_de_rutas <archivo> <ruta>...: el archivo es una ruta o cuelga de ella
  local archivo="$1" r
  shift
  for r in "$@"; do
    r="${r#./}"
    r="${r%/}"
    [ "$archivo" = "$r" ] || [[ "$archivo" == "$r"/* ]] && return 0
  done
  return 1
}

python_bin() {
  if [ -n "${PYTHON:-}" ]; then printf '%s\n' "$PYTHON"; return 0; fi
  local c
  for c in venv/Scripts/python.exe venv/bin/python python3 python; do
    if { [ -x "$c" ] || command -v "$c" >/dev/null 2>&1; } && "$c" -c 'import sys' >/dev/null 2>&1; then
      printf '%s\n' "$c"
      return 0
    fi
  done
  return 1
}

paso0() {
  local rama="${1:-${ITOS_BRANCH:-}}"
  [ -n "$rama" ] || die "Indica la rama: bash scripts/git_strategy.sh 0 <fix|feat>/<slug>"
  validar_rama "$rama"
  local actual
  actual=$(rama_actual)
  if [ "$actual" = "$rama" ]; then
    echo "✅ Ya estás en $rama (WIP intacto)."
  elif git show-ref --verify --quiet "refs/heads/$rama"; then
    git checkout "$rama"
    echo "✅ Cambiado a $rama (rama ya existía)."
  else
    git checkout -b "$rama"
    echo "✅ Rama $rama creada desde '$actual' (WIP arrastrado, sin commitear)."
  fi
}

paso1() {
  local mensajes=() rutas=()
  while [ $# -gt 0 ]; do
    case "$1" in
      -m)
        [ $# -ge 2 ] && [ -n "$2" ] || die "Falta el texto después de -m."
        mensajes+=("$2"); shift 2 ;;
      --)
        shift; rutas=("$@"); break ;;
      *)
        die "Argumento inesperado: '$1'. Uso: 1 -m \"<mensaje>\" -- <ruta>..." ;;
    esac
  done
  [ ${#mensajes[@]} -gt 0 ] || die "Falta el mensaje (-m): el script no inventa mensajes de commit."
  [ ${#rutas[@]} -gt 0 ] || die "Declara las rutas a commitear después de '--'."

  local actual
  actual=$(rama_actual)
  [ "$actual" != "$MAIN" ] || die "Estás en $MAIN: nunca se commitea directo (regla absoluta 4). Usa el paso 0."
  validar_rama "$actual"

  local r
  for r in "${rutas[@]}"; do
    case "$r" in
      .|./|*'*'*|:*|-*) die "Ruta no permitida: '$r'. Declara archivos o carpetas concretos (sin '.', '-A', comodines ni pathspecs mágicos)." ;;
    esac
  done
  # El commit incluye todo el índice: lo preparado de antemano (p. ej. un cambio de modo con
  # `git update-index --chmod=+x`) solo se admite si cae dentro de las rutas declaradas.
  # Con core.filemode=true (Linux, macOS) el `git add` de abajo toma el modo del disco:
  # ahí el +x se da con `chmod +x`, no solo en el índice.
  local preparado
  while IFS= read -r preparado; do
    [ -n "$preparado" ] || continue
    dentro_de_rutas "$preparado" "${rutas[@]}" ||
      die "'$preparado' ya está preparado y no es una ruta declarada; revisa 'git diff --cached' antes del paso 1."
  done < <(git diff --cached --name-only)

  # --literal-pathspecs: git no interpreta comodines ni pathspecs mágicos en las rutas.
  if ! git --literal-pathspecs add -- "${rutas[@]}"; then
    git reset -q -- "${rutas[@]}" 2>/dev/null || true
    die "No se pudieron preparar las rutas declaradas; no se commiteó nada."
  fi
  if git diff --cached --quiet; then
    die "Las rutas declaradas no tienen cambios."
  fi

  local py
  py=$(python_bin) || { git reset -q -- "${rutas[@]}"; die "No hay intérprete de Python para verificar la política de datos (define PYTHON)."; }
  if ! "$py" scripts/check_sensitive_paths.py; then
    git reset -q -- "${rutas[@]}"
    die "Política de datos incumplida: se deshizo la preparación y no se commiteó nada."
  fi

  echo "── Cambios a commitear en $actual ──"
  git diff --cached --stat
  local args=() m
  for m in "${mensajes[@]}"; do args+=(-m "$m"); done
  git commit "${args[@]}"
  echo "✅ Commit creado en $actual."
}

paso2() {
  local actual
  actual=$(rama_actual)
  [ "$actual" != "$MAIN" ] || die "El paso 2 publica ramas de trabajo, no $MAIN."
  validar_rama "$actual"
  git push -u origin "$actual"
  echo "✅ Push de $actual a origin."
}

gates() {
  local py="$1" s
  if [ -d tests ]; then
    "$py" -m unittest discover -s tests -p "test_*.py" || { echo "❌ Gate fallido: unittest" >&2; return 1; }
  fi
  for s in scripts/check_agent_surfaces.py scripts/check_sensitive_paths.py \
           scripts/evaluate_gold_set.py scripts/evaluate_plan_gold_set.py; do
    if [ -f "$s" ]; then
      "$py" "$s" || { echo "❌ Gate fallido: $s" >&2; return 1; }
    fi
  done
}

paso3() {
  local confirmar="" extra=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --confirmar) [ $# -ge 2 ] || die "Falta la rama después de --confirmar."; confirmar="$2"; shift 2 ;;
      -m) [ $# -ge 2 ] && [ -n "$2" ] || die "Falta el texto después de -m."; extra+=(-m "$2"); shift 2 ;;
      *) die "Argumento inesperado: '$1'. Uso: 3 [--confirmar <rama>] [-m \"<párrafo>\"]..." ;;
    esac
  done

  local rama
  rama=$(rama_actual)
  [ "$rama" != "$MAIN" ] || die "Cámbiate a la rama de trabajo que quieres fusionar."
  validar_rama "$rama"
  # --ignore-submodules=dirty: el contenido modificado dentro de un submódulo no bloquea,
  # pero un cambio de su puntero (commit referenciado) sí cuenta como pendiente.
  git diff --quiet --ignore-submodules=dirty && git diff --cached --quiet --ignore-submodules=dirty ||
    die "Hay cambios sin commitear en $rama; commitea o descártalos antes del merge."

  if [ -n "$confirmar" ]; then
    [ "$confirmar" = "$rama" ] || die "--confirmar '$confirmar' no coincide con la rama actual '$rama'."
  elif [ -t 0 ]; then
    printf "⚠️  Vas a fusionar %s -> %s. Escribe el nombre de la rama para confirmar: " "$rama" "$MAIN"
    local ans
    read -r ans
    [ "$ans" = "$rama" ] || die "Cancelado."
  else
    die "Sin terminal interactiva: usa --confirmar $rama, solo por instrucción explícita del operador."
  fi

  local py
  py=$(python_bin) || die "No hay intérprete de Python para los gates (define PYTHON)."
  gates "$py" || die "Gates fallidos: no se fusionó nada."

  local titulo
  titulo=$(git log -1 --format=%s "$rama")
  git checkout "$MAIN"
  git merge --no-ff "$rama" -m "Merge $rama: $titulo" "${extra[@]}"
  echo "✅ Merge a $MAIN completo. Pendiente y manual: run_regression.py (requiere corpus) y el push de $MAIN."
}

uso() {
  sed -n '7,17p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
}

step="${1:-}"
[ $# -gt 0 ] && shift
case "$step" in
  0) paso0 "$@" ;;
  1) paso1 "$@" ;;
  2) paso2 "$@" ;;
  3) paso3 "$@" ;;
  *) uso ;;
esac
