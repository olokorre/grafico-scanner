"""Interface grafica (Tkinter) do grafico-scanner."""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from . import charts, fonts, parser, veiculos
from .analysis import Resumo, analisar, detectar_proporcoes
from .mapview import PainelMapa
from .parser import LogData


class Aplicativo(tk.Tk):
    """Janela principal do grafico-scanner."""

    def __init__(self, arquivos_iniciais: list[str] | None = None) -> None:
        super().__init__()
        self.title("grafico-scanner")
        self.geometry("1280x820")
        self.minsize(1000, 640)
        fonts.aplicar_tk(self)

        self.logs: list[LogData] = []
        self._carregando = False
        self._fila: queue.Queue = queue.Queue()
        self._log_atual: LogData | None = None
        self._veiculos = veiculos.carregar()
        self._nome_veiculo = tk.StringVar(value="Automático")

        self._montar_menu()
        self._montar_layout()
        self.protocol("WM_DELETE_WINDOW", self._fechar)

        if arquivos_iniciais:
            self.after(200, lambda: self.carregar(arquivos_iniciais))

    # ------------------------------------------------------------------ layout
    def _montar_menu(self) -> None:
        menu = tk.Menu(self)
        arquivos = tk.Menu(menu, tearoff=0)
        arquivos.add_command(label="Abrir CSV...", accelerator="Ctrl+O",
                             command=self.abrir_dialogo)
        arquivos.add_command(label="Combinar selecionados",
                             command=self.combinar_selecionados)
        arquivos.add_separator()
        arquivos.add_command(label="Sair", command=self.destroy)
        menu.add_cascade(label="Arquivo", menu=arquivos)

        veiculo_menu = tk.Menu(menu, tearoff=0)
        veiculo_menu.add_radiobutton(
            label="Automático (detectar)", variable=self._nome_veiculo,
            value="Automático", command=self._trocar_veiculo,
        )
        veiculo_menu.add_separator()
        for nome in self._veiculos:
            veiculo_menu.add_radiobutton(
                label=nome, variable=self._nome_veiculo, value=nome,
                command=self._trocar_veiculo,
            )
        veiculo_menu.add_separator()
        veiculo_menu.add_command(
            label="Salvar proporções deste log como veículo...",
            command=self._salvar_veiculo_log,
        )
        menu.add_cascade(label="Veículo", menu=veiculo_menu)

        ajuda = tk.Menu(menu, tearoff=0)
        ajuda.add_command(label="Sobre", command=self._sobre)
        menu.add_cascade(label="Ajuda", menu=ajuda)
        self.config(menu=menu)
        self.bind("<Control-o>", lambda _e: self.abrir_dialogo())

    # ------------------------------------------------------------- veiculo
    def _veiculo_atual(self):
        """Perfil de veiculo selecionado ou ``None`` (deteccao automatica)."""
        if self._nome_veiculo.get() == "Automático":
            return None
        return self._veiculos.get(self._nome_veiculo.get())

    def _trocar_veiculo(self) -> None:
        if self._log_atual is not None:
            self._renderizar(self._log_atual)

    def _salvar_veiculo_log(self) -> None:
        if self._log_atual is None:
            messagebox.showinfo("Salvar veículo", "Nenhum arquivo carregado.")
            return
        nome = simpledialog.askstring(
            "Salvar veículo",
            "Nome do veículo (ex.: Polo Flex 1.6 2005 manual):",
            parent=self,
        )
        if not nome:
            return
        proporcoes = detectar_proporcoes(self._log_atual)
        if not proporcoes:
            messagebox.showwarning(
                "Salvar veículo",
                "Não foi possível detectar as marchas neste log "
                "(RPM/velocidade insuficientes).",
            )
            return
        try:
            veiculos.salvar_perfil(nome.strip(), proporcoes)
        except OSError as exc:  # noqa: BLE001
            messagebox.showerror("Salvar veículo", f"Falha ao gravar: {exc}")
            return
        self._veiculos = veiculos.carregar()
        self._nome_veiculo.set(nome.strip())
        self._montar_menu()
        self._trocar_veiculo()
        messagebox.showinfo(
            "Salvar veículo",
            f"Perfil '{nome.strip()}' salvo em {veiculos.CAMINHO_PADRAO}.",
        )

    def _montar_layout(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        lateral = ttk.Frame(self, padding=6)
        lateral.grid(row=0, column=0, sticky="ns")
        lateral.rowconfigure(3, weight=1)

        ttk.Label(lateral, text="Arquivos carregados",
                  font=(fonts.FAMILIA_UI, 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 4))

        botoes = ttk.Frame(lateral)
        botoes.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        ttk.Button(botoes, text="Abrir CSV...", command=self.abrir_dialogo).pack(
            side="left", fill="x", expand=True)
        ttk.Button(botoes, text="Combinar", command=self.combinar_selecionados).pack(
            side="left", fill="x", expand=True, padx=(4, 0))

        self.lista = tk.Listbox(lateral, width=34, exportselection=False,
                                selectmode="extended", font=(fonts.FAMILIA_UI, 10))
        self.lista.grid(row=3, column=0, sticky="nsew")
        self.lista.bind("<<ListboxSelect>>", self._ao_selecionar)
        barra_lista = ttk.Scrollbar(lateral, orient="vertical",
                                    command=self.lista.yview)
        barra_lista.grid(row=3, column=1, sticky="ns")
        self.lista.config(yscrollcommand=barra_lista.set)

        self._dica = ttk.Label(lateral, text="Selecione um arquivo para visualizar",
                               wraplength=230, foreground="#666")
        self._dica.grid(row=4, column=0, sticky="ew", pady=(4, 0))

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=1, sticky="nsew")

        self.aba_resumo = ttk.Frame(self.notebook, padding=0)
        self.aba_velocidade = ttk.Frame(self.notebook)
        self.aba_consumo = ttk.Frame(self.notebook)
        self.aba_desempenho = ttk.Frame(self.notebook)
        self.aba_marchas = ttk.Frame(self.notebook)
        self.aba_economia = ttk.Frame(self.notebook)
        self.aba_motor = ttk.Frame(self.notebook)
        self.aba_percurso = ttk.Frame(self.notebook)
        self.aba_mapa = ttk.Frame(self.notebook)

        self.notebook.add(self.aba_resumo, text="Resumo")
        self.notebook.add(self.aba_velocidade, text="Velocidade e RPM")
        self.notebook.add(self.aba_consumo, text="Consumo e potencia")
        self.notebook.add(self.aba_desempenho, text="Desempenho (dyno)")
        self.notebook.add(self.aba_marchas, text="Marchas")
        self.notebook.add(self.aba_economia, text="Economia")
        self.notebook.add(self.aba_motor, text="Motor e ambiente")
        self.notebook.add(self.aba_percurso, text="Percurso acumulado")
        self.notebook.add(self.aba_mapa, text="Mapa do trajeto")

        self.mapa = PainelMapa(self.aba_mapa)
        self.mapa.pack(fill="both", expand=True)

        self._montar_resumo_rolavel()

        status = ttk.Frame(self)
        status.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.progresso = ttk.Progressbar(status, mode="determinate", length=200)
        self.progresso.pack(side="left", padx=6, pady=3)
        self.status = tk.StringVar(value="Pronto")
        ttk.Label(status, textvariable=self.status).pack(side="left")

        self._configurar_estilo()

    def _montar_resumo_rolavel(self) -> None:
        """Cria canvas rolavel na aba Resumo (conteudo grande)."""
        canvas = tk.Canvas(self.aba_resumo, highlightthickness=0)
        barra = ttk.Scrollbar(self.aba_resumo, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=barra.set)
        canvas.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")

        self._resumo_canvas = canvas
        self._resumo_corpo = ttk.Frame(canvas, padding=10)
        self._resumo_janela = canvas.create_window((0, 0), window=self._resumo_corpo,
                                                   anchor="nw")

        def _ajustar(_evento=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(self._resumo_janela, width=canvas.winfo_width())

        self._resumo_corpo.bind("<Configure>", _ajustar)
        canvas.bind("<Configure>", _ajustar)

        # Rolagem com a roda do mouse apenas quando a aba Resumo esta ativa.
        self.bind_all("<MouseWheel>", self._rolar_resumo)
        self.bind_all("<Button-4>", self._rolar_resumo)
        self.bind_all("<Button-5>", self._rolar_resumo)

    def _rolar_resumo(self, evento) -> None:
        if self.notebook.select() != str(self.aba_resumo):
            return
        numero = getattr(evento, "num", None)
        if numero == 4:
            passo = -1
        elif numero == 5:
            passo = 1
        else:
            passo = -1 if getattr(evento, "delta", 0) > 0 else 1
        self._resumo_canvas.yview_scroll(passo, "units")

    def _configurar_estilo(self) -> None:
        estilo = ttk.Style(self)
        if "clam" in estilo.theme_names():
            estilo.theme_use("clam")
        estilo.configure("Cartao.TFrame", background="#f4f6fb", relief="flat")
        estilo.configure("Titulo.TLabel", font=(fonts.FAMILIA_UI, 11, "bold"))
        estilo.configure("Valor.TLabel", font=(fonts.FAMILIA_UI, 12, "bold"),
                         foreground="#1f6feb")
        estilo.configure("Rotulo.TLabel", foreground="#444")

    # ------------------------------------------------------------ carregamento
    def abrir_dialogo(self) -> None:
        caminhos = filedialog.askopenfilenames(
            title="Selecione o(s) arquivo(s) CSV",
            filetypes=[("CSV", "*.csv"), ("Todos os arquivos", "*.*")],
        )
        if caminhos:
            self.carregar(list(caminhos))

    def carregar(self, caminhos: list[str]) -> None:
        if self._carregando:
            messagebox.showinfo("Aguarde", "Ja existe um carregamento em andamento.")
            return
        self._carregando = True
        self.progresso["value"] = 0
        self.status.set("Iniciando leitura...")
        threading.Thread(target=self._worker, args=(caminhos,), daemon=True).start()
        self.after(80, self._processar_fila)

    def _worker(self, caminhos: list[str]) -> None:
        for caminho in caminhos:
            nome = os.path.basename(caminho)
            try:
                total = parser.contar_linhas(caminho)

                def progresso(atual: int, tot: int, nome: str = nome) -> None:
                    self._fila.put(("progresso", nome, atual, tot))

                log = parser.ler_csv(caminho, progresso)
            except Exception as exc:  # noqa: BLE001
                self._fila.put(("erro", nome, str(exc)))
                continue
            self._fila.put(("log", log))
        self._fila.put(("fim", None))

    def _processar_fila(self) -> None:
        try:
            while True:
                mensagem = self._fila.get_nowait()
                self._tratar_mensagem(mensagem)
        except queue.Empty:
            pass
        if self._carregando:
            self.after(80, self._processar_fila)

    def _tratar_mensagem(self, mensagem: tuple) -> None:
        tipo = mensagem[0]
        if tipo == "progresso":
            self._atualizar_progresso(mensagem[1], mensagem[2], mensagem[3])
        elif tipo == "log":
            self._adicionar_log(mensagem[1])
        elif tipo == "erro":
            messagebox.showerror("Erro ao ler arquivo", f"{mensagem[1]}:\n{mensagem[2]}")
        elif tipo == "fim":
            self._fim_carregamento()

    def _atualizar_progresso(self, nome: str, atual: int, total: int) -> None:
        pct = (atual / total * 100) if total else 0
        self.progresso["value"] = pct
        self.status.set(f"Lendo {nome}: {atual:,}/{total:,} linhas".replace(",", "."))

    def _adicionar_log(self, log: LogData) -> None:
        self.logs.append(log)
        self.lista.insert("end", log.nome)
        self.status.set(f"Carregado: {log.nome} "
                        f"({len(log.df):,} registros)".replace(",", "."))
        if self.lista.size() == 1:
            self.lista.selection_set(0)
            self._ao_selecionar()

    def _fim_carregamento(self) -> None:
        self._carregando = False
        self.progresso["value"] = 0

    # -------------------------------------------------------------- selecao
    def _ao_selecionar(self, _evento=None) -> None:
        selecao = self.lista.curselection()
        if not selecao:
            return
        log = self.logs[selecao[0]]
        self._log_atual = log
        self.status.set(f"Exibindo: {log.nome}")
        self._renderizar(log)

    def combinar_selecionados(self) -> None:
        selecao = self.lista.curselection()
        if len(selecao) < 2:
            messagebox.showinfo(
                "Combinar",
                "Selecione dois ou mais arquivos (Ctrl+clique) na lista.",
            )
            return
        import pandas as pd

        quadros = []
        offset = 0.0
        for indice in selecao:
            log = self.logs[indice]
            if log.nome.startswith("Combinado"):
                continue
            quadro = log.df.copy()
            quadro["tempo"] = quadro["tempo"] + offset
            offset += log.duracao_s + 1.0
            quadros.append(quadro)
        if not quadros:
            return
        df = pd.concat(quadros, ignore_index=True)
        nome = f"Combinado ({len(quadros)} arquivos)"
        combinado = LogData(nome, nome, df, 0.0, offset,
                            sorted(df["parametro"].unique().tolist()))
        self.logs.append(combinado)
        self.lista.insert("end", nome)
        self.lista.selection_clear(0, "end")
        self.lista.selection_set("end")
        self._ao_selecionar()

    # -------------------------------------------------------------- render
    def _renderizar(self, log: LogData) -> None:
        resumo = analisar(log, self._veiculo_atual())
        self._render_resumo(log, resumo)

        self._embutir(self.aba_velocidade, charts.figura_velocidade_rpm(log))
        self._embutir(self.aba_consumo, charts.figura_consumo_potencia(log))
        self._embutir(self.aba_desempenho, charts.figura_dyno(log))
        self._embutir(self.aba_marchas, charts.figura_marchas(log, self._veiculo_atual()))
        self._embutir(self.aba_economia, charts.figura_consumo_velocidade(log))
        self._embutir(self.aba_motor, charts.figura_motor_ambiente(log))
        self._embutir(self.aba_percurso, charts.figura_percurso(log))
        self.mapa.atualizar(log)

    def _embutir(self, frame: ttk.Frame, fig: Figure) -> None:
        for filho in frame.winfo_children():
            filho.destroy()
        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.draw()
        barra = NavigationToolbar2Tk(canvas, frame, pack_toolbar=False)
        barra.update()
        barra.pack(side="bottom", fill="x")
        canvas.get_tk_widget().pack(fill="both", expand=True)

    def _render_resumo(self, log: LogData, resumo: Resumo) -> None:
        for filho in self._resumo_corpo.winfo_children():
            filho.destroy()

        cabecalho = ttk.Frame(self._resumo_corpo)
        cabecalho.pack(fill="x", pady=(0, 8))
        ttk.Label(cabecalho, text=log.nome, style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(
            cabecalho,
            text=f"{len(log.df):,} registros | {len(log.parametros)} parametros".replace(",", "."),
            style="Rotulo.TLabel",
        ).pack(anchor="w")

        grade = ttk.Frame(self._resumo_corpo)
        grade.pack(fill="both", expand=True)

        colunas = 2
        for indice, (rotulo, valor) in enumerate(resumo.rotulos):
            linha, coluna = divmod(indice, colunas)
            cartao = ttk.Frame(grade, style="Cartao.TFrame", padding=10)
            cartao.grid(row=linha, column=coluna, sticky="nsew", padx=5, pady=5)
            ttk.Label(cartao, text=rotulo, style="Rotulo.TLabel").pack(anchor="w")
            ttk.Label(cartao, text=valor, style="Valor.TLabel").pack(anchor="w")
            grade.columnconfigure(coluna, weight=1)

        if not any(v for _r, v in resumo.rotulos if v != "--"):
            ttk.Label(self._resumo_corpo, text="Sem dados reconhecidos neste arquivo.").pack()

        aviso = self._aviso_gps(log)
        if aviso:
            ttk.Label(self._resumo_corpo, text=aviso, foreground="#b45309",
                      wraplength=760).pack(anchor="w", pady=(8, 0))

    @staticmethod
    def _aviso_gps(log: LogData) -> str:
        pontos = log.df[["lat", "lon"]].dropna()
        if len(pontos) < 2:
            return "GPS: sem coordenadas validas neste log."
        amplitude = max(pontos["lat"].max() - pontos["lat"].min(),
                        pontos["lon"].max() - pontos["lon"].min())
        if amplitude < 0.01:
            return ("Aviso: as coordenadas GPS variam muito pouco neste log; "
                    "o mapa do trajeto pode ser impreciso.")
        return ""

    # ------------------------------------------------------------- utilidades
    def _fechar(self) -> None:
        self._carregando = False
        try:
            for identificador in self.tk.call("after", "info"):
                try:
                    self.tk.call("after", "cancel", identificador)
                except tk.TclError:
                    pass
        except tk.TclError:
            pass
        self.quit()
        self.destroy()

    def _sobre(self) -> None:
        messagebox.showinfo(
            "Sobre",
            "grafico-scanner\n\n"
            "Le logs CSV de scanner OBD-II e exibe distancia percorrida, "
            "velocidades, consumo, graficos de uso e mapa do trajeto.",
        )


def executar(arquivos: list[str] | None = None) -> None:
    app = Aplicativo(arquivos)
    app.mainloop()
