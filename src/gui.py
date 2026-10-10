"""TurboPlay — GUI: front-end de jogos (PC + emulados).

Visual de launcher de verdade: tema escuro, capas, grade de cards, busca e
filtros por provedor. A interface usa tkinter; capas locais dependem de Pillow.

Princípio de honestidade visual: um jogo bloqueado (Game Pass, pasta sem
escrita, anti-cheat) aparece com o motivo — nunca com um ✓ enganoso.
"""
from __future__ import annotations

import subprocess
import threading
import tkinter as tk
from collections import Counter
from pathlib import Path
from tkinter import ttk

from .applier import verify_fork_integrity
from .covers import fallback_identity, get_cover, set_cover
from .classifier import classify
from .consolelib import scan_console_library
from .emulaunch import launch_emulated
from .emuperf import apply_system_upgrades
from .launcher import launch, post_launch_watch, pre_launch
from .notify import notify
from .pipeline import get_library, rollback_all
from .providers import scan_all
from .searchlib import search_library
from .watcher import LibraryWatcher, auto_optimize_new_games
from . import autostart as _autostart

_SAMBOX = Path(r"D:\Games\SAMBOX-Vfull")

# ── paleta (escuro, launcher) ────────────────────────────────────────────────
BG        = "#0d1117"
BG_PANEL  = "#161b22"
BG_CARD   = "#1c2128"
BG_HOVER  = "#262d36"
FG        = "#e6edf3"
FG_DIM    = "#8b949e"
ACCENT    = "#2ea043"
ACCENT_HI = "#3fb950"
LOCKED    = "#d29922"
DANGER    = "#f85149"
BORDER    = "#30363d"


class TurboPlayApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("TurboPlay")
        self.root.geometry("1180x760")
        self.root.minsize(980, 640)
        self.root.configure(bg=BG)

        self.games: list[dict] = []
        self.console_items: list[dict] = []
        self._console_rows: list[tuple] = []
        self._cards: list[tuple[tk.Frame, dict]] = []
        self._cover_images: dict[str, tuple[tuple[str, int, int, int], tk.PhotoImage]] = {}

        self._build()
        self._style()
        threading.Thread(target=self._load_all, daemon=True).start()
        self._watcher = LibraryWatcher(on_change=self._on_library_changed,
                                       poll_sec=20)
        threading.Thread(target=self._watcher.loop, daemon=True).start()

    # ── estilo ────────────────────────────────────────────────────────────────
    def _style(self) -> None:
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=BG_PANEL, foreground=FG_DIM,
                    padding=(22, 10), borderwidth=0)
        s.map("TNotebook.Tab",
              background=[("selected", BG)],
              foreground=[("selected", FG)])
        s.configure("Play.TButton", background=ACCENT, foreground="white",
                    font=("Segoe UI", 11, "bold"), borderwidth=0, padding=(14, 9))
        s.map("Play.TButton",
              background=[("active", ACCENT_HI), ("disabled", "#21262d")],
              foreground=[("disabled", "#6e7681")])
        s.configure("Flat.TButton", background=BG_CARD, foreground=FG_DIM,
                    borderwidth=0, padding=(8, 5))
        s.map("Flat.TButton", background=[("active", BG_HOVER)],
              foreground=[("active", FG)])

    # ── layout ────────────────────────────────────────────────────────────────
    def _build(self) -> None:
        # topo
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill=tk.X, padx=18, pady=(16, 10))

        tk.Label(top, text="TURBOPLAY", bg=BG, fg=FG,
                 font=("Segoe UI", 21, "bold")).pack(side=tk.LEFT)
        tk.Label(top, text="  otimização automática · DLSS 5 + MFG",
                 bg=BG, fg=FG_DIM, font=("Segoe UI", 10)).pack(side=tk.LEFT, pady=(8, 0))

        self.var_search = tk.StringVar()
        self.var_search.trace_add("write", lambda *_: self._on_search())
        ent = tk.Entry(top, textvariable=self.var_search, font=("Segoe UI", 11),
                       bg=BG_PANEL, fg=FG, insertbackground=FG,
                       relief="flat", highlightthickness=1,
                       highlightbackground=BORDER, highlightcolor=ACCENT,
                       width=26)
        ent.pack(side=tk.RIGHT, ipady=7, padx=(0, 0))
        tk.Label(top, text="🔍", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 12)).pack(side=tk.RIGHT, padx=(0, 8))

        # abas
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=14)

        self.tab_pc = tk.Frame(self.nb, bg=BG)
        self.nb.add(self.tab_pc, text="   🖥️   JOGOS PC   ")
        self._build_pc_tab()

        self.tab_console = tk.Frame(self.nb, bg=BG)
        self.nb.add(self.tab_console, text="   🕹️   CONSOLES   ")
        self._build_console_tab()

        # rodapé
        foot = tk.Frame(self.root, bg=BG_PANEL, height=34)
        foot.pack(fill=tk.X, side=tk.BOTTOM)
        foot.pack_propagate(False)
        self.status = tk.Label(foot, text="Carregando…", bg=BG_PANEL, fg=FG_DIM,
                               font=("Segoe UI", 9), anchor="w")
        self.status.pack(side=tk.LEFT, padx=14)
        ttk.Button(foot, text="↩  Reverter tudo", style="Flat.TButton",
                   command=self._on_rollback).pack(side=tk.RIGHT, padx=(0, 10), pady=5)
        self.btn_auto = ttk.Button(foot, text="⚙  Iniciar com o Windows", style="Flat.TButton",
                                   command=self._on_toggle_autostart)
        self.btn_auto.pack(side=tk.RIGHT, pady=5)
        self.root.after(300, self._refresh_autostart_btn)

    def _refresh_autostart_btn(self) -> None:
        on = _autostart.is_enabled()
        self.btn_auto.configure(text="⚙  Autostart: LIGADO" if on
                               else "⚙  Autostart: desligado")

    def _on_toggle_autostart(self) -> None:
        enable = not _autostart.is_enabled()
        ok = _autostart.set_enabled(enable)
        if enable:
            self.status.configure(
                text="Atalho criado na pasta Inicializar — o TurboPlay vigia sozinho."
                if ok else "Não consegui criar o atalho.")
        else:
            self.status.configure(text="Autostart desligado." if ok
                                  else "Não consegui remover o atalho.")
        self._refresh_autostart_btn()

    # ── aba PC: grade de cards ────────────────────────────────────────────────
    def _build_pc_tab(self) -> None:
        bar = tk.Frame(self.tab_pc, bg=BG)
        bar.pack(fill=tk.X, padx=14, pady=(10, 6))
        self.var_filter = tk.StringVar(value="Todos")
        for f in ("Todos", "Otimizados", "Bloqueados"):
            ttk.Button(bar, text=f, style="Flat.TButton",
                       command=lambda v=f: self._set_filter(v)).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bar, text="🧩  Instalar mod…", style="Flat.TButton",
                   command=self._on_install_mod).pack(side=tk.LEFT, padx=(16, 6))
        self.lbl_count = tk.Label(bar, text="", bg=BG, fg=FG_DIM, font=("Segoe UI", 9))
        self.lbl_count.pack(side=tk.RIGHT)

        body = tk.Frame(self.tab_pc, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 12))
        self.grid_host = tk.Frame(body, bg=BG)
        self.grid_host.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(self.grid_host, bg=BG, highlightthickness=0)
        self.scroll = ttk.Scrollbar(self.grid_host, orient="vertical",
                                    command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.cards_frame = tk.Frame(self.canvas, bg=BG)
        self._win = self.canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")
        self.cards_frame.bind("<Configure>",
                              lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._on_wheel, add="+")

    def _on_wheel(self, event) -> None:
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _set_filter(self, value: str) -> None:
        self.var_filter.set(value)
        self._render_pc_grid()

    def _on_search(self) -> None:
        self.nb.select(self.tab_pc if not self.var_search.get().strip()
                       else self.tab_console)
        self._render_pc_grid()
        self._render_console_list(self.console_items, self.var_search.get().strip())

    def _card(self, g: dict) -> tk.Frame:
        """Um card de jogo: capa, título, provedor e estado."""
        f = tk.Frame(self.cards_frame, bg=BG_CARD, highlightthickness=1,
                     highlightbackground=BORDER, width=200, height=250)
        blocked = g.get("blocked")
        ok = g.get("optimized")

        # capa
        cover = tk.Frame(f, bg=BG_HOVER, height=130)
        cover.pack(fill=tk.X)
        cover.pack_propagate(False)
        # capas manuais são locais; ID inválido/corrompido apenas usa a genérica.
        try:
            cover_path = get_cover(g.get("id", ""))
        except ValueError:
            cover_path = None
        if cover_path:
            try:
                image = self._cover_photo(g.get("id", ""), cover_path)
                image_label = tk.Label(cover, image=image, bg=BG_HOVER)
                image_label.image = image
                image_label.pack(expand=True)
            except (OSError, tk.TclError):
                self._cover_images.pop(g.get("id", ""), None)
                self._cover_placeholder(cover, g.get("id", ""), g["title"])
        else:
            self._cover_images.pop(g.get("id", ""), None)
            self._cover_placeholder(cover, g.get("id", ""), g["title"])

        tk.Label(f, text=g["title"][:26], bg=BG_CARD, fg=FG,
                 font=("Segoe UI", 10, "bold"), anchor="w",
                 wraplength=180, justify=tk.LEFT).pack(fill=tk.X, padx=10, pady=(8, 2))
        tag = _SOURCE_LABEL.get(g["source"], g["source"])
        tk.Label(f, text=tag, bg=BG_CARD, fg=FG_DIM, font=("Segoe UI", 8),
                 anchor="w").pack(fill=tk.X, padx=10)
        if blocked:
            tk.Label(f, text="Não otimizável", bg=BG_CARD, fg=LOCKED,
                     font=("Segoe UI", 8, "bold"), anchor="w").pack(fill=tk.X, padx=10)
        elif ok:
            tk.Label(f, text="✓ DLSS 5 + MFG", bg=BG_CARD, fg=ACCENT_HI,
                     font=("Segoe UI", 8, "bold"), anchor="w").pack(fill=tk.X, padx=10)

        ttk.Button(f, text="Capa…", style="Flat.TButton",
                   command=lambda game=g: self._on_choose_cover(game)).pack(
                       anchor="w", padx=7, pady=(4, 5))
        f.bind("<Double-Button-1>", lambda e, gg=g: self._play_native(gg))
        f.bind("<Enter>", lambda e: f.configure(highlightbackground=ACCENT, bg=BG_HOVER))
        f.bind("<Leave>", lambda e: f.configure(highlightbackground=BORDER, bg=BG_CARD))
        for child in f.winfo_children():
            if isinstance(child, ttk.Button):
                continue
            child.bind("<Double-Button-1>", lambda e, gg=g: self._play_native(gg))
        return f

    def _cover_photo(self, game_id: str, path: Path) -> tk.PhotoImage:
        """Carrega/redimensiona uma capa uma vez; invalida por stat e identidade."""
        stat = path.stat()
        signature = (str(path), stat.st_size, stat.st_mtime_ns, stat.st_ino)
        cached = self._cover_images.get(game_id)
        if cached is not None and cached[0] == signature:
            return cached[1]
        image = tk.PhotoImage(file=str(path))
        factor = max(1, (image.width() + 199) // 200,
                     (image.height() + 129) // 130)
        if factor > 1:
            image = image.subsample(factor, factor)
        self._cover_images[game_id] = (signature, image)
        return image

    def _cover_placeholder(self, parent: tk.Frame, game_id: str, title: str) -> None:
        """Capa genérica local, visualmente estável e explicitamente não oficial."""
        background, accent = fallback_identity(game_id, title)
        parent.configure(bg=background)
        tk.Label(parent, text="CAPA LOCAL · NÃO OFICIAL", bg=background, fg=accent,
                 font=("Segoe UI", 8, "bold")).pack(anchor="nw", padx=10, pady=(10, 2))
        tk.Label(parent, text=(title or "Jogo")[:34], bg=background, fg=FG,
                 font=("Segoe UI", 13, "bold"), wraplength=176,
                 justify=tk.LEFT, anchor="w").pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        tk.Label(parent, text="TURBOPLAY", bg=background, fg=accent,
                 font=("Segoe UI", 8, "bold")).pack(anchor="se", padx=10, pady=(0, 8))

    def _on_choose_cover(self, game: dict) -> None:
        from tkinter import filedialog, messagebox
        if getattr(self, "_cover_dialog_open", False):
            return
        self._cover_dialog_open = True
        try:
            source = filedialog.askopenfilename(
                parent=self.root, title=f"Escolher capa — {game['title']}",
                filetypes=[("Imagens PNG ou GIF", "*.png *.gif")])
        finally:
            self._cover_dialog_open = False
        if not source:
            return
        try:
            set_cover(game["id"], source)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Capa inválida", str(exc), parent=self.root)
            return
        self.status.configure(text=f"Capa atualizada: {game['title']}")
        self._render_pc_grid()

    def _render_pc_grid(self) -> None:
        for w in self.cards_frame.winfo_children():
            w.destroy()
        self._cards = []
        filt = self.var_filter.get()
        q = self.var_search.get().strip().lower()
        items = []
        for g in self.games:
            if filt == "Otimizados" and not g.get("optimized"):
                continue
            if filt == "Bloqueados" and not g.get("blocked"):
                continue
            if q and q not in g["title"].lower() and q not in g["source"].lower():
                continue
            items.append(g)
        cols = 5
        for i, g in enumerate(items):
            c = self._card(g)
            c.grid(row=i // cols, column=i % cols, padx=7, pady=7, sticky="nsew")
            self._cards.append((c, g))
        for col in range(cols):
            self.cards_frame.grid_columnconfigure(col, weight=1, uniform="card")
        self.lbl_count.configure(text=f"{len(items)} de {len(self.games)}")

    # ── aba consoles ──────────────────────────────────────────────────────────
    def _build_console_tab(self) -> None:
        pane = tk.Frame(self.tab_console, bg=BG)
        pane.pack(fill=tk.BOTH, expand=True, padx=14, pady=(12, 12))
        left = tk.Frame(pane, bg=BG)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        right = tk.Frame(pane, bg=BG_PANEL, width=290)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        right.pack_propagate(False)

        self.list_console = tk.Listbox(left, font=("Segoe UI", 10), bg=BG_PANEL, fg=FG,
                                       selectbackground="#238636", selectforeground="white",
                                       activestyle="none", highlightthickness=1,
                                       highlightbackground=BORDER, borderwidth=0)
        self.list_console.pack(fill=tk.BOTH, expand=True)
        self.list_console.bind("<<ListboxSelect>>", self._on_console_select)
        self.list_console.bind("<Double-Button-1>", lambda e: self._play_console())

        tk.Label(right, text="CONSOLE", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(14, 4))
        self.lbl_sys = tk.Label(right, text="", bg=BG_PANEL, fg=FG, font=("Segoe UI", 12, "bold"),
                                justify=tk.LEFT, anchor="w", wraplength=255)
        self.lbl_sys.pack(anchor="w", padx=14)
        tk.Label(right, text="MELHORIAS DISPONÍVEIS", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(18, 4))
        self.lbl_upgrades = tk.Label(right, text="", bg=BG_PANEL, fg=ACCENT_HI,
                                     font=("Segoe UI", 9), justify=tk.LEFT,
                                     anchor="w", wraplength=255)
        self.lbl_upgrades.pack(anchor="w", padx=14)
        self.btn_play_c = ttk.Button(right, text="▶   JOGAR", style="Play.TButton",
                                     state=tk.DISABLED, command=self._play_console)
        self.btn_play_c.pack(anchor="w", padx=14, pady=(22, 0))

    def _render_console_list(self, items: list[dict], q: str) -> None:
        self.list_console.delete(0, tk.END)
        self._console_rows = []
        if q:
            hits, desc = search_library(self.console_items, q)
            self.list_console.insert(tk.END, f"  🔍  {len(hits)} resultado(s) — {desc}")
            self._console_rows.append(("header", None))
            by: dict[str, list[dict]] = {}
            for it in hits:
                by.setdefault(it["system_name"], []).append(it)
            for name in sorted(by):
                self.list_console.insert(tk.END, f"  ▸ {name}  ({len(by[name])})")
                self._console_rows.append(("header", None))
                for it in sorted(by[name], key=lambda x: x["title"].lower()):
                    self.list_console.insert(tk.END, f"      {it['title']}")
                    self._console_rows.append(("game", it))
            return
        by = {}
        for it in items:
            by.setdefault(f"{it['gen']:02d}|{it['system_name']}", []).append(it)
        for key in sorted(by):
            gen_s, name = key.split("|", 1)
            first = by[key][0]
            gen = f"G{gen_s}" if gen_s != "00" else "—"
            self.list_console.insert(tk.END,
                                     f"  ▸ {name}   ({len(by[key])})   [{gen}]   {first['emu']}")
            self._console_rows.append(("header", None))
            for it in sorted(by[key], key=lambda x: x["title"].lower()):
                self.list_console.insert(tk.END, f"      {it['title']}")
                self._console_rows.append(("game", it))

    def _on_console_select(self, _e=None) -> None:
        sel = self.list_console.curselection()
        if not sel or self._console_rows[sel[0]][0] != "game":
            return
        it = self._console_rows[sel[0]][1]
        self.lbl_sys.configure(text=f"{it['system_name']}\nGeração {it['gen'] or '—'}\n{it['emu']}")
        ups = "\n".join(f"• {u}" for u in it["upgrades"]) or "• padrão do emulador"
        self.lbl_upgrades.configure(text=ups)
        self.btn_play_c.configure(state=tk.NORMAL)

    # ── ações ─────────────────────────────────────────────────────────────────
    def _play_native(self, g: dict) -> None:
        self._play_flow(g["id"], g["title"], launch_path=g["launch_path"])

    def _play_console(self) -> None:
        sel = self.list_console.curselection()
        if not sel or self._console_rows[sel[0]][0] != "game":
            self.status.configure(text="Selecione um jogo 👆")
            return
        it = self._console_rows[sel[0]][1]
        self._play_flow(it["id"], it["title"], console_item=it)

    def _play_flow(self, gid: str, title: str, launch_path: str = "",
                   console_item: dict | None = None) -> None:
        self.status.configure(text=f"Preparando {title}…")

        def work() -> None:
            try:
                game_obj = None
                if console_item is None:
                    pre_launch({"id": gid})
                    game_obj = next((classify(c) for c in scan_all() if c.id == gid), None)
                    if game_obj:
                        # mods da biblioteca mods/<Jogo>/ — 1x por mod
                        try:
                            from .mods import auto_install_for_game
                            installed = auto_install_for_game(
                                game_obj.title, game_obj.folder,
                                Path(game_obj.exe_path).name)
                            for name in installed:
                                self._log_safe(f"🧩 {title}: mod '{name}' instalado")
                        except Exception:
                            pass
                    popen, err = launch(game_obj) if game_obj else (None, "não encontrado")
                else:
                    if console_item.get("bat"):
                        popen, err = None, ""
                        subprocess.Popen(["cmd", "/c", console_item["bat"]],
                                         creationflags=subprocess.CREATE_NO_WINDOW)
                    else:
                        try:
                            ups = apply_system_upgrades(console_item["system"])
                            if ups:
                                self._log_safe(f"{console_item['system']}: {len(ups)} ajustes")
                        except Exception:
                            pass
                        popen, err = launch_emulated(console_item["rom"],
                                                     console_item["emu"],
                                                     console_item["system"])
                if popen is None and err:
                    self.root.after(0, lambda: self.status.configure(
                        text=f"Não consegui abrir {title}: {err}"))
                    return
                self._log_safe(f"{title} iniciado")
                self.root.after(0, lambda: self.status.configure(
                    text=f"{title} rodando — bom jogo!"))
                if console_item is None and game_obj:
                    post_launch_watch(game_obj, popen)
            except Exception as e:
                self.root.after(0, lambda: self.status.configure(text=f"Erro: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def _log_safe(self, msg: str) -> None:
        notify("TurboPlay", msg)

    def _on_rollback(self) -> None:
        def work() -> None:
            n = rollback_all()
            self.root.after(0, lambda: self.status.configure(
                text=f"{n} jogo(s) revertido(s)."))
            self.root.after(0, lambda: threading.Thread(
                target=self._load_all, daemon=True).start())
        threading.Thread(target=work, daemon=True).start()

    # ── mods ────────────────────────────────────────────────────────────────
    def _on_install_mod(self) -> None:
        """Diálogo: escolhe o jogo → escolhe o zip/RAR → instala."""
        from tkinter import simpledialog, filedialog, messagebox
        import src.mods as mods
        if not self.games:
            messagebox.showinfo("TurboPlay", "Nenhum jogo na biblioteca ainda.")
            return
        titles = sorted(g["title"] for g in self.games)
        choice = simpledialog.askstring(
            "Instalar mod",
            "Pra qual jogo? (digite parte do nome):\n"
            + "\n".join(titles[:12]) + ("\n…" if len(titles) > 12 else ""),
            parent=self.root)
        if not choice or not choice.strip():
            return
        q = choice.strip().lower()
        matches = [g for g in self.games if q in g["title"].lower()]
        if not matches:
            messagebox.showerror("TurboPlay", f"Nenhum jogo casa com '{choice}'.")
            return
        if len(matches) > 1:
            opts = "\n".join(f"{i+1}. {g['title']}" for i, g in enumerate(matches))
            pick = simpledialog.askstring(
                "Instalar mod", f"Vários jogos casam:\n{opts}\n\nNúmero:",
                parent=self.root)
            try:
                g = matches[int(pick) - 1]
            except (ValueError, TypeError, IndexError):
                return
        else:
            g = matches[0]
        arc = filedialog.askopenfilename(
            title=f"Mod para {g['title']}",
            filetypes=[("Mods", "*.zip *.rar *.7z"), ("Todos", "*.*")])
        if not arc:
            return
        self.status.configure(text=f"Instalando mod em {g['title']}…")

        def work() -> None:
            folder = self._game_folder(g["id"])
            r = mods.install_mod(g["title"], folder, arc)
            msg = (f"🧩 {g['title']}: mod '{r.name}' — "
                   + (f"{r.error}" if r.ok else f"FALHOU: {r.error}"))
            self._log_safe(msg)
            self.root.after(0, lambda: self.status.configure(text=msg))
        threading.Thread(target=work, daemon=True).start()

    def _game_folder(self, gid: str) -> str:
        for c in scan_all():
            if c.id == gid:
                return c.folder
        return ""

    # ── carga ─────────────────────────────────────────────────────────────────
    def _on_library_changed(self) -> None:
        try:
            res = auto_optimize_new_games()
            for title, dec in res["applied"]:
                notify("TurboPlay", f"Novo jogo otimizado: {title} ({dec})")
            self.root.after(0, lambda: threading.Thread(
                target=self._load_all, daemon=True).start())
        except Exception:
            pass

    def _load_all(self) -> None:
        try:
            games = get_library()
            consoles = scan_console_library(_SAMBOX)
            stack_ok, stack_why = verify_fork_integrity()

            def render() -> None:
                self.games, self.console_items = games, consoles
                self._render_pc_grid()
                self._render_console_list(consoles, self.var_search.get().strip())
                provs = " · ".join(f"{_SOURCE_LABEL.get(k, k)} {v}" for k, v
                                  in sorted(Counter(g["source"] for g in games).items()))
                opt = sum(1 for g in games if g.get("optimized"))
                blocked = sum(1 for g in games if g.get("blocked"))
                nsys = len({i["system"] for i in consoles})
                msg = f"{len(games)} jogo(s) PC  ({provs or '—'})   ·   {opt} otimizado(s)"
                if blocked:
                    msg += f"   ·   {blocked} bloqueado(s)"
                msg += f"   ·   {len(consoles)} jogos de console em {nsys} sistemas"
                self.status.configure(text=msg if stack_ok
                                      else "⚠  Stack DLSS5+MFG: " + stack_why)
            self.root.after(0, render)
        except Exception as e:
            self.root.after(0, lambda: self.status.configure(text=f"Erro: {e}"))

    def run(self) -> None:
        self.root.mainloop()


_SOURCE_LABEL = {"sambox": "SAMBOX", "steam": "Steam", "xbox": "Game Pass",
                 "epic": "Epic", "gog": "GOG", "custom": "Pasta"}


def main() -> None:
    TurboPlayApp().run()


if __name__ == "__main__":
    main()