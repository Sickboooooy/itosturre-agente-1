#!/usr/bin/env bash
# git_strategy.sh — disciplina de ramas para la corrección P0 de integridad del corpus.
#
# Mueve el WIP fuera de main, lo commitea en una rama, lo empuja y (con confirmación
# explícita) lo fusiona a main. Nunca usa --force ni --no-verify.
#
# Uso:
#   bash scripts/git_strategy.sh 0   # crear/cambiar a la rama de trabajo (arrastra el WIP)
#   bash scripts/git_strategy.sh 1   # stage + commit en la rama
#   bash scripts/git_strategy.sh 2   # push de la rama a origin
#   bash scripts/git_strategy.sh 3   # merge --no-ff de la rama a main (pide confirmación)
#
# Override de nombre de rama:  ITOS_BRANCH=otra/rama bash scripts/git_strategy.sh 0
set -euo pipefail

BRANCH="${ITOS_BRANCH:-fix/corpus-integrity-vvca}"
MAIN="${ITOS_MAIN:-main}"
step="${1:-}"

case "$step" in
  0)
    current=$(git branch --show-current)
    if [ "$current" = "$BRANCH" ]; then
      echo "✅ Ya estás en $BRANCH (WIP intacto)."
    elif git show-ref --verify --quiet "refs/heads/$BRANCH"; then
      git checkout "$BRANCH"
      echo "✅ Cambiado a $BRANCH (rama ya existía)."
    else
      git checkout -b "$BRANCH"
      echo "✅ Rama $BRANCH creada desde '$current' (WIP arrastrado, sin commitear)."
    fi
    ;;
  1)
    # Stage SOLO los archivos del P0. Evita 'git add -A' a propósito: no arrastra
    # services/ (trabajo no relacionado) ni casos_de_prueba/ (posibles datos de
    # cliente real — esos van en commits aparte o se mantienen fuera de git).
    git add .gitignore OpenNotebook.py scoring_vvca.py vvca_full.py \
            scripts/check_corpus.py scripts/git_strategy.sh \
            README.md CONTRIBUTING.md CLAUDE.md docs/PROTOCOLO_VVCA.md
    echo "── Cambios a commitear (scopeados al P0): ──"
    git status --short
    git commit -m "fix(corpus): cerrar brecha LGV/PIDCP + guards anti-falso-veredicto VVCA

- Re-index LGV y PIDCP (mapeadas en LAW_SOURCE_MAP pero ausentes del índice ChromaDB)
- EXCLUDE_PATTERNS: excluir compilaciones *_Tesis_Completas del corpus estatutario
- audit(): ley resuelta-pero-ausente -> 🟡 NO VERIFICABLE (ya no 🔴 'alucinación')
- audit(): artículo sin ley en el contexto -> 🟡 advertencia (ya no 🟢 ciego)
- scoring_vvca: separar tesis_discrepantes (🔴 bloqueante) de tesis_no_encontradas (🟡)
- COSINE_THRESHOLD 0.50 -> 0.25 (validado contra casos_de_prueba)
- scripts/check_corpus.py + scripts/git_strategy.sh + vvca_full.py

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
    echo "✅ Commit creado en $BRANCH."
    ;;
  2)
    git push -u origin "$BRANCH"
    echo "✅ Push de $BRANCH a origin."
    ;;
  3)
    echo "⚠️  Vas a fusionar $BRANCH -> $MAIN."
    printf "   Escribe 'merge' para confirmar: "
    read -r ans
    [ "$ans" = "merge" ] || { echo "Cancelado."; exit 1; }
    git checkout "$MAIN"
    git merge --no-ff "$BRANCH" -m "Merge $BRANCH: integridad del corpus VVCA (P0)"
    echo "✅ Merge a $MAIN completo. Haz push de $MAIN cuando quieras."
    ;;
  *)
    echo "Uso: bash scripts/git_strategy.sh {0|1|2|3}"
    echo "  0 = rama de trabajo   1 = commit   2 = push   3 = merge a $MAIN"
    exit 1
    ;;
esac
