"""Painel de mapa do trajeto, com fallback para Matplotlib.

Tenta usar :mod:`tkintermapview` (tiles OpenStreetMap, requer internet). Se o
pacote ou os tiles nao estiverem disponiveis, desenha o trajeto com Matplotlib.
O trajeto pode ser colorido por uma variavel (velocidade, RPM, consumo, boost).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import numpy as np

from .charts import COR_FUNDO, COR_GRADE, COR_PAINEL, COR_TEXTO, PALETA
from .parser import P, LogData

try:  # pragma: no cover - depende do ambiente
    from tkintermapview import TkinterMapView

    TEM_MAPA = True
except Exception:  # noqa: BLE001
    TkinterMapView = None  # type: ignore[assignment,misc]
    TEM_MAPA = False

VARIAVEIS_MAPA: dict[str, str] = {
    "Velocidade": P.velocidade,
    "RPM": P.rpm,
    "Consumo (L/h)": P.consumo_lh,
    "Boost (bar)": P.boost,
}

MAX_SEGMENTOS = 400


class PainelMapa(ttk.Frame):
    """Widget que exibe o trajeto do log selecionado."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self._log: LogData | None = None
        self.mapa = None
        self._canvas = None
        self._fig: Figure | None = None
        self._aviso = tk.StringVar(value="Nenhum arquivo carregado")
        self._variavel = tk.StringVar(value="Velocidade")

        self._construir()

    def _construir(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        topo = ttk.Frame(self)
        topo.grid(row=0, column=0, sticky="ew", padx=6, pady=4)
        ttk.Label(topo, textvariable=self._aviso).pack(side="left")
        ttk.Button(topo, text="Redesenhar", command=self._redesenhar).pack(side="right")
        ttk.Label(topo, text="Colorir por:").pack(side="right", padx=(0, 4))
        combo = ttk.Combobox(
            topo, textvariable=self._variavel, values=list(VARIAVEIS_MAPA),
            state="readonly", width=14,
        )
        combo.pack(side="right", padx=(0, 8))
        combo.bind("<<ComboboxSelected>>", lambda _e: self._redesenhar())

        self.area = ttk.Frame(self)
        self.area.grid(row=1, column=0, sticky="nsew")

        if TEM_MAPA:
            try:
                self.mapa = TkinterMapView(self.area, corner_radius=0)
                self.mapa.pack(fill="both", expand=True)
            except Exception:  # noqa: BLE001
                self.mapa = None

    def _dados_trajeto(self):
        dados = self._log.df[["tempo", "lat", "lon"]].dropna()
        dados = dados[(dados["lat"].abs() > 0.0001) & (dados["lon"].abs() > 0.0001)]
        dados = dados[(dados["lat"] < 90) & (dados["lat"] > -90)]
        dados = dados.drop_duplicates(subset=["lat", "lon"]).sort_values("tempo")
        return dados.reset_index(drop=True)

    def _valores(self, tempos: np.ndarray) -> np.ndarray | None:
        if self._log is None:
            return None
        parametro = VARIAVEIS_MAPA.get(self._variavel.get())
        if parametro is None or not self._log.tem(parametro):
            return None
        serie = self._log.serie(parametro)
        if serie.empty:
            return None
        t = serie["tempo"].to_numpy(dtype=float)
        v = serie["valor"].to_numpy(dtype=float)
        if t.size < 2:
            return None
        return np.interp(tempos, t, v)

    @staticmethod
    def _amostrar(max_n: int, *arrays: np.ndarray):
        n = len(arrays[0])
        if n <= max_n:
            return arrays
        indices = np.linspace(0, n - 1, max_n).astype(int)
        return tuple(array[indices] for array in arrays)

    def atualizar(self, log: LogData) -> None:
        self._log = log
        self._redesenhar()

    def _redesenhar(self) -> None:
        if self._log is None:
            self._aviso.set("Nenhum arquivo carregado")
            return

        coords = self._dados_trajeto()
        if len(coords) < 2:
            self._aviso.set("Coordenadas GPS insuficientes neste log")
            self._limpar()
            return

        lats = coords["lat"].to_numpy(dtype=float)
        lons = coords["lon"].to_numpy(dtype=float)
        tempos = coords["tempo"].to_numpy(dtype=float)
        valores = self._valores(tempos)

        if valores is not None:
            lats, lons, valores = self._amostrar(MAX_SEGMENTOS, lats, lons, valores)
        else:
            lats, lons = self._amostrar(MAX_SEGMENTOS, lats, lons)
        pontos = list(zip(lats.tolist(), lons.tolist()))

        rotulo = self._variavel.get() if valores is not None else "trajeto"
        self._aviso.set(f"Trajeto com {len(coords)} pontos GPS ({rotulo})")

        if self.mapa is not None:
            self._desenhar_mapa(pontos, valores)
        else:
            self._desenhar_matplotlib(pontos, valores)

    def _limpar(self) -> None:
        if self.mapa is not None:
            self.mapa.delete_all_path()
            self.mapa.delete_all_marker()
        if self._canvas is not None:
            self._canvas.get_tk_widget().destroy()
            self._canvas = None
        if self._fig is not None:
            plt.close(self._fig)
            self._fig = None

    def _cores(self, valores: np.ndarray | None) -> tuple[list, object]:
        cmap = matplotlib.colormaps["turbo"]
        if valores is None or np.nanmax(valores) == np.nanmin(valores):
            return [], cmap
        norm = matplotlib.colors.Normalize(vmin=float(np.nanmin(valores)),
                                           vmax=float(np.nanmax(valores)))
        return [cmap(norm(v)) for v in valores], cmap

    def _desenhar_mapa(self, pontos: list[tuple[float, float]], valores) -> None:
        try:
            self.mapa.delete_all_path()
            self.mapa.delete_all_marker()
            self.mapa.set_position(pontos[0][0], pontos[0][1])
            self.mapa.set_zoom(15)

            cores, _ = self._cores(valores)
            if not cores:
                self.mapa.set_path(pontos, color=PALETA[0], width=3)
            else:
                for i in range(len(pontos) - 1):
                    cor = matplotlib.colors.to_hex(cores[i])
                    self.mapa.set_path([pontos[i], pontos[i + 1]], color=cor, width=3)

            self.mapa.set_marker(pontos[0][0], pontos[0][1], text="Inicio")
            self.mapa.set_marker(pontos[-1][0], pontos[-1][1], text="Fim")
        except Exception as exc:  # noqa: BLE001
            self._aviso.set(f"Falha ao desenhar mapa ({exc}); usando fallback")
            self._desenhar_matplotlib(pontos, valores)

    def _desenhar_matplotlib(self, pontos: list[tuple[float, float]], valores) -> None:
        self._limpar()
        lats = [p[0] for p in pontos]
        lons = [p[1] for p in pontos]

        fig = Figure(figsize=(6, 4.5), dpi=100)
        ax = fig.add_subplot(111)
        fig.patch.set_facecolor(COR_FUNDO)
        ax.set_facecolor(COR_PAINEL)

        cores, cmap = self._cores(valores)
        if not cores:
            ax.plot(lons, lats, color=PALETA[0], linewidth=1.6)
        else:
            segmentos = [
                [(lons[i], lats[i]), (lons[i + 1], lats[i + 1])]
                for i in range(len(pontos) - 1)
            ]
            colecao = LineCollection(segmentos, colors=cores, linewidth=2)
            ax.add_collection(colecao)
            ax.autoscale_view()
            barra = fig.colorbar(colecao, ax=ax, fraction=0.04, pad=0.02)
            barra.set_label(self._variavel.get(), color=COR_TEXTO, fontsize=8)
            barra.ax.yaxis.set_tick_params(color=COR_TEXTO, labelsize=7)

        ax.scatter([lons[0]], [lats[0]], color=PALETA[2], zorder=3, label="Inicio")
        ax.scatter([lons[-1]], [lats[-1]], color=PALETA[1], zorder=3, label="Fim")
        ax.set_xlabel("Longitude", color=COR_TEXTO)
        ax.set_ylabel("Latitude", color=COR_TEXTO)
        ax.set_title("Trajeto (GPS)", color=COR_TEXTO)
        ax.tick_params(colors=COR_TEXTO, labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(COR_GRADE)
        ax.grid(True, color=COR_GRADE, alpha=0.35, linewidth=0.6)
        legen = ax.legend(fontsize=7)
        legen.get_frame().set_facecolor(COR_PAINEL)

        self._fig = fig
        self._canvas = FigureCanvasTkAgg(fig, master=self.area)
        self._canvas.draw()
        self._canvas.get_tk_widget().pack(fill="both", expand=True)
