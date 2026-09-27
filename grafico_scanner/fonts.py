"""Selecao de fontes do aplicativo, com fallback seguro.

Prefere fontes como Noto Sans; se nenhuma estiver instalada, mantem o
comportamento padrao do Tkinter e do Matplotlib.
"""

from __future__ import annotations

import tkinter.font as tkfont
from typing import Iterable

FAMILIAS_PREFERIDAS = [
    "Noto Sans",
    "Cantarell",
    "DejaVu Sans",
    "Liberation Sans",
]

FAMILIA_UI = FAMILIAS_PREFERIDAS[0]
FAMILIA_MONO = "Noto Sans Mono"
FAMILIAS_MONO = ["Noto Sans Mono", "DejaVu Sans Mono", "Liberation Mono"]

_NOMEADAS = (
    "TkDefaultFont",
    "TkTextFont",
    "TkMenuFont",
    "TkHeadingFont",
    "TkTooltipFont",
)


def familia_disponivel(disponiveis: Iterable[str], preferidas: list[str]) -> str | None:
    """Retorna a grafia real da primeira familia preferida disponivel.

    A comparacao ignora maiusculas/minusculas, pois o Tkinter reporta os
    nomes em minusculas.
    """
    indice = {nome.lower(): nome for nome in disponiveis}
    for familia in preferidas:
        achada = indice.get(familia.lower())
        if achada is not None:
            return achada
    return None


def familia_tk(root) -> str | None:
    """Detecta uma familia instalada visivel para o Tkinter."""
    try:
        disponiveis = set(tkfont.families(root))
    except Exception:  # noqa: BLE001
        return None
    return familia_disponivel(disponiveis, FAMILIAS_PREFERIDAS)


def aplicar_tk(root) -> str:
    """Configura as fontes nomeadas do Tkinter para a familia escolhida.

    Retorna a familia aplicada (ou o padrao do sistema se nenhuma preferida
    estiver instalada).
    """
    global FAMILIA_UI

    familia = familia_tk(root)
    if familia is None:
        return FAMILIA_UI

    FAMILIA_UI = familia
    for nome in _NOMEADAS:
        try:
            fonte = tkfont.nametofont(nome, root=root)
            fonte.configure(family=familia)
        except Exception:  # noqa: BLE001
            continue

    disponiveis = set(tkfont.families(root))
    mono = familia_disponivel(disponiveis, FAMILIAS_MONO)
    if mono is not None:
        try:
            tkfont.nametofont("TkFixedFont", root=root).configure(family=mono)
        except Exception:  # noqa: BLE001
            pass
    return familia


def aplicar_matplotlib() -> None:
    """Aplica a familia escolhida as figuras do Matplotlib."""
    import matplotlib
    import matplotlib.font_manager as fm

    disponiveis = {f.name for f in fm.fontManager.ttflist}
    familia = familia_disponivel(disponiveis, FAMILIAS_PREFERIDAS)
    if familia is None:
        return

    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = FAMILIAS_PREFERIDAS
    matplotlib.rcParams["axes.unicode_minus"] = False
