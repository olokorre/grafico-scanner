#!/usr/bin/env bash
#
# Cria a venv (com o Python 3.13, unico neste sistema com Tkinter disponivel),
# instala as dependencias e executa o grafico-scanner.
#
set -euo pipefail

cd "$(dirname "$0")"

# O python3 do sistema (3.14) nao possui tkinter e nao pode receber rpm.
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  for candidato in \
      "$HOME/.local/bin/python3.13" \
      "$HOME/.asdf/shims/python3.13" \
      "$(command -v python3.13 2>/dev/null || true)" \
      "$(command -v python3 2>/dev/null || true)"; do
    if [ -n "$candidato" ] && [ -x "$candidato" ] && \
       "$candidato" -c "import tkinter" >/dev/null 2>&1; then
      PYTHON="$candidato"
      break
    fi
  done
fi

if [ -z "$PYTHON" ]; then
  echo "Nenhum Python com Tkinter encontrado." >&2
  echo "Defina PYTHON=/caminho/python3.13 e rode novamente." >&2
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Criando venv com $PYTHON ..."
  "$PYTHON" -m venv .venv
  ./.venv/bin/pip install --upgrade pip >/dev/null
  ./.venv/bin/pip install -r requirements.txt
fi

exec ./.venv/bin/python main.py "$@"
