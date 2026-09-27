"""Construcao das figuras Matplotlib usadas na interface."""

from __future__ import annotations

import os

import matplotlib

if not os.environ.get("MPLBACKEND"):
    try:
        matplotlib.use("TkAgg")
    except Exception:  # noqa: BLE001
        matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import numpy as np
import pandas as pd

from . import analysis
from . import fonts
from .parser import P, LogData

fonts.aplicar_matplotlib()

COR_FUNDO = "#1e1e2e"
COR_PAINEL = "#2a2a3c"
COR_TEXTO = "#e0e0e8"
COR_GRADE = "#3a3a50"
PALETA = ["#89b4fa", "#f38ba8", "#a6e3a1", "#f9e2af", "#cba6f7", "#94e2d5", "#fab387"]


def _minutos(serie: pd.DataFrame) -> np.ndarray:
    return serie["tempo"].to_numpy(dtype=float) / 60.0


def _estilizar(fig: Figure) -> None:
    fig.patch.set_facecolor(COR_FUNDO)
    for ax in fig.axes:
        ax.set_facecolor(COR_PAINEL)
        ax.tick_params(colors=COR_TEXTO, labelsize=8)
        ax.xaxis.label.set_color(COR_TEXTO)
        ax.yaxis.label.set_color(COR_TEXTO)
        ax.title.set_color(COR_TEXTO)
        for spine in ax.spines.values():
            spine.set_color(COR_GRADE)
        ax.grid(True, color=COR_GRADE, alpha=0.35, linewidth=0.6)
        leg = ax.get_legend()
        if leg is not None:
            leg.get_frame().set_facecolor(COR_PAINEL)
            leg.get_frame().set_edgecolor(COR_GRADE)
            for texto in leg.get_texts():
                texto.set_color(COR_TEXTO)


def _plot(ax, serie: pd.DataFrame, rotulo: str, cor: str, largura: float = 1.2):
    if serie.empty:
        return
    ax.plot(_minutos(serie), serie["valor"].to_numpy(dtype=float), color=cor,
            linewidth=largura, label=rotulo)


def _vazio(ax, mensagem: str = "Parametro ausente no arquivo"):
    ax.text(0.5, 0.5, mensagem, transform=ax.transAxes, ha="center", va="center",
            color=COR_TEXTO, fontsize=10)


def _finalizar(fig: Figure, ax_legenda) -> Figure:
    _estilizar(fig)
    if ax_legenda is not None:
        handles, labels = ax_legenda.get_legend_handles_labels()
        if handles:
            ax_legenda.legend(loc="upper left", fontsize=7, framealpha=0.9)
    return fig


def figura_velocidade_rpm(log: LogData) -> Figure:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.set_xlabel("tempo (min)")
    ax.set_ylabel("Velocidade (km/h)", color=PALETA[0])
    _plot(ax, log.serie(P.velocidade), "Velocidade do veiculo", PALETA[0])
    ax.tick_params(axis="y", labelcolor=PALETA[0])

    ax2 = ax.twinx()
    ax2.set_ylabel("RPM", color=PALETA[1])
    _plot(ax2, log.serie(P.rpm), "RPM do motor", PALETA[1])
    ax2.tick_params(axis="y", labelcolor=PALETA[1])
    ax2.tick_params(colors=COR_TEXTO, labelsize=8)
    ax2.grid(False)

    linhas1, rot1 = ax.get_legend_handles_labels()
    linhas2, rot2 = ax2.get_legend_handles_labels()
    if linhas1 or linhas2:
        ax.legend(linhas1 + linhas2, rot1 + rot2, loc="upper left", fontsize=7)
    ax.set_title("Velocidade e RPM")
    return _finalizar(fig, ax)


def figura_consumo_potencia(log: LogData) -> Figure:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.set_xlabel("tempo (min)")
    ax.set_ylabel("Consumo (L/h)", color=PALETA[0])
    _plot(ax, log.serie(P.consumo_lh), "Consumo instantaneo (L/h)", PALETA[0])
    ax.tick_params(axis="y", labelcolor=PALETA[0])

    ax2 = ax.twinx()
    ax2.set_ylabel("Potencia (hp)", color=PALETA[2])
    _plot(ax2, log.serie(P.potencia), "Potencia instantanea (hp)", PALETA[2])
    ax2.tick_params(axis="y", labelcolor=PALETA[2])
    ax2.tick_params(colors=COR_TEXTO, labelsize=8)
    ax2.grid(False)

    linhas1, rot1 = ax.get_legend_handles_labels()
    linhas2, rot2 = ax2.get_legend_handles_labels()
    if linhas1 or linhas2:
        ax.legend(linhas1 + linhas2, rot1 + rot2, loc="upper left", fontsize=7)
    ax.set_title("Consumo e potencia do motor")
    return _finalizar(fig, ax)


def figura_motor_ambiente(log: LogData) -> Figure:
    fig, axs = plt.subplots(2, 2, figsize=(8, 5.5))
    fig.subplots_adjust(hspace=0.45, wspace=0.3)

    ax = axs[0][0]
    ax.set_title("Aceleracao", fontsize=9)
    ax.set_xlabel("tempo (min)", fontsize=8)
    _plot(ax, log.serie(P.aceleracao), "g", PALETA[3], 0.8)
    if log.serie(P.aceleracao).empty:
        _vazio(ax)

    ax = axs[0][1]
    ax.set_title("Posicao da borboleta", fontsize=9)
    ax.set_xlabel("tempo (min)", fontsize=8)
    _plot(ax, log.serie(P.borboleta), "%", PALETA[4], 0.8)
    if log.serie(P.borboleta).empty:
        _vazio(ax)

    ax = axs[1][0]
    ax.set_title("Pressao do coletor (MAP)", fontsize=9)
    ax.set_xlabel("tempo (min)", fontsize=8)
    _plot(ax, log.serie(P.map_kpa), "MAP (kPa)", PALETA[5], 0.9)
    if not log.serie(P.map_kpa).empty:
        ax.legend(fontsize=7, loc="upper left")
    else:
        _vazio(ax)

    ax = axs[1][1]
    ax.set_title("Temperatura do ar de admissao", fontsize=9)
    ax.set_xlabel("tempo (min)", fontsize=8)
    _plot(ax, log.serie(P.temperatura_ar), "°C", PALETA[6], 1.0)
    if log.serie(P.temperatura_ar).empty:
        _vazio(ax)

    for ax in axs.flat:
        ax.tick_params(labelsize=7)

    return _finalizar(fig, None)


def figura_percurso(log: LogData) -> Figure:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.set_xlabel("tempo (min)")
    ax.set_ylabel("Distancia (km)", color=PALETA[0])

    dist = log.serie(P.distancia)
    if not dist.empty:
        acumulado = dist["valor"].cummax().to_numpy(dtype=float)
        ax.plot(_minutos(dist), acumulado, color=PALETA[0], linewidth=1.4,
                label="Distancia acumulada (km)")
    else:
        _vazio(ax)

    ax2 = ax.twinx()
    ax2.set_ylabel("Combustivel (L)", color=PALETA[2])
    comb = log.serie(P.combustivel_total) if log.tem(P.combustivel_total) else log.serie(P.combustivel_usado)
    if not comb.empty:
        usado = comb["valor"].to_numpy(dtype=float)
        base = usado - usado[0]
        ax2.plot(_minutos(comb), base, color=PALETA[2], linewidth=1.4,
                 label="Combustivel usado (L)")
    ax2.tick_params(axis="y", labelcolor=PALETA[2])
    ax2.tick_params(colors=COR_TEXTO, labelsize=8)
    ax2.grid(False)

    linhas1, rot1 = ax.get_legend_handles_labels()
    linhas2, rot2 = ax2.get_legend_handles_labels()
    if linhas1 or linhas2:
        ax.legend(linhas1 + linhas2, rot1 + rot2, loc="upper left", fontsize=7)
    ax.set_title("Percurso acumulado")
    return _finalizar(fig, ax)


def figura_dyno(log: LogData) -> Figure:
    """Curva de potencia e torque estimados por faixa de RPM (dyno virtual)."""
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.set_xlabel("RPM")
    ax.set_ylabel("Potencia (hp)", color=PALETA[2])
    ax.tick_params(axis="y", labelcolor=PALETA[2])

    curva = analysis.curva_dyno(log)

    ax2 = ax.twinx()
    ax2.set_ylabel("Torque (Nm)", color=PALETA[1])
    ax2.tick_params(axis="y", labelcolor=PALETA[1])
    ax2.tick_params(colors=COR_TEXTO, labelsize=8)
    ax2.grid(False)

    if not curva.empty:
        ax.plot(curva["rpm"], curva["hp"], color=PALETA[2], marker="o", ms=3,
                linewidth=1.6, label="Potencia (hp)")
        ax2.plot(curva["rpm"], curva["torque"], color=PALETA[1], marker="s", ms=3,
                 linewidth=1.6, label="Torque (Nm)")
        linhas1, rot1 = ax.get_legend_handles_labels()
        linhas2, rot2 = ax2.get_legend_handles_labels()
        ax.legend(linhas1 + linhas2, rot1 + rot2, loc="upper left", fontsize=7)
    else:
        _vazio(ax, "Potencia/RPM ausentes no arquivo")

    ax.set_title("Potencia e torque estimados")
    return _finalizar(fig, None)


def figura_marchas(log: LogData, veiculo=None) -> Figure:
    """Marcha estimada ao longo do tempo e tempo total em cada marcha."""
    fig, axs = plt.subplots(1, 2, figsize=(9, 4.2))
    fig.subplots_adjust(wspace=0.3)

    serie = analysis.serie_marchas(log, veiculo)
    stats = analysis.estatisticas_marchas(serie)

    ax = axs[0]
    ax.set_title("Marcha ao longo do tempo", fontsize=9)
    ax.set_xlabel("tempo (min)", fontsize=8)
    ax.set_ylabel("marcha", fontsize=8)
    if not serie.empty:
        ax.step(_minutos(serie), serie["marcha"].to_numpy(dtype=float),
                where="post", color=PALETA[4], linewidth=1.2)
        maximo = int(serie["marcha"].max())
        ax.set_yticks(range(1, maximo + 1))
    else:
        _vazio(ax, "RPM/velocidade insuficientes")

    ax = axs[1]
    ax.set_title("Tempo por marcha", fontsize=9)
    ax.set_ylabel("tempo (min)", fontsize=8)
    tempos = stats["tempo_por_marcha"]
    if tempos:
        ax.bar([f"{m}a" for m in tempos], [v / 60.0 for v in tempos.values()],
               color=PALETA[0])
    else:
        _vazio(ax, "Sem marchas detectadas")

    return _finalizar(fig, None)


def figura_consumo_velocidade(log: LogData) -> Figure:
    """Rendimento (km/L) em funcao da velocidade, com a faixa mais economica."""
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.set_xlabel("Velocidade (km/h)")
    ax.set_ylabel("Rendimento (km/L)", color=PALETA[2])

    if not (log.tem(P.velocidade) and log.tem(P.consumo_lh)):
        _vazio(ax, "Consumo/velocidade ausentes no arquivo")
        return _finalizar(fig, ax)

    base = log.alinhar(P.velocidade, P.consumo_lh)
    vel = base[P.velocidade].to_numpy(dtype=float)
    lh = base[P.consumo_lh].to_numpy(dtype=float)
    valido = (lh > 0.05) & (vel > 10)
    if valido.sum() < 10:
        _vazio(ax, "Amostras insuficientes em movimento")
        return _finalizar(fig, ax)

    kml = vel[valido] / lh[valido]
    ax.scatter(vel[valido], kml, s=5, color=PALETA[0], alpha=0.25, label="Amostras")

    binned = analysis.consumo_por_velocidade(log)
    if not binned.empty:
        ax.plot(binned["velocidade"], binned["km_l"], color=PALETA[1], marker="o",
                linewidth=1.8, label="Mediana por faixa")
        indice = binned["km_l"].to_numpy(dtype=float).argmax()
        vel_otima = float(binned["velocidade"].iloc[indice])
        rend_otimo = float(binned["km_l"].iloc[indice])
        ax.scatter([vel_otima], [rend_otimo], color=PALETA[2], s=70, zorder=5,
                   label=f"Otimo ~{vel_otima:.0f} km/h")

    limite = float(np.nanpercentile(kml, 98))
    if np.isfinite(limite) and limite > 0:
        ax.set_ylim(0, limite * 1.2)
    ax.legend(loc="upper left", fontsize=7)
    ax.set_title("Rendimento por velocidade")
    return _finalizar(fig, ax)
