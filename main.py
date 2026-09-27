#!/usr/bin/env python3
"""Ponto de entrada do grafico-scanner.

Uso::

    python main.py                    # abre o ultimo/primeiro CSV da pasta
    python main.py "arquivo.csv"      # abre um ou mais arquivos
    python main.py a.csv b.csv
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

from grafico_scanner.app import executar


def _csvs_padrao() -> list[str]:
    """Retorna o CSV mais recente da pasta atual, se houver."""
    arquivos = sorted(glob.glob("*.csv"), key=os.path.getmtime, reverse=True)
    return arquivos[:1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Visualizador de logs OBD-II")
    parser.add_argument("arquivos", nargs="*", help="Arquivos CSV para carregar")
    args = parser.parse_args(argv)

    arquivos = args.arquivos or _csvs_padrao()
    for caminho in arquivos:
        if not os.path.isfile(caminho):
            print(f"Arquivo nao encontrado: {caminho}", file=sys.stderr)
            return 1

    executar(arquivos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
