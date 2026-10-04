"""TurboPlay — GUI v3: console virtual com jogos nativos + todos os emulados.

Aba "Meus Jogos": jogos PC nativos (Steam/SAMBOX) com stack MFG/DLSS.
Aba "Consoles": jogos emulados agrupados por videogame (PS1, PS2, SNES...)
com as melhorias disponíveis mostradas no painel.
"""
from __future__ import annotations

import subprocess
import threading
import tkinter as tk
from collections import Counter
from tkinter import scrolledtext, ttk

from .launcher import launch, post_launch_watch, pre_launch
from .notify import notify
from .pipeline import get_library, rollback_all
from .consolelib import scan_console_library, system_summary
from .emulaunch import launch_emulated
from .providers import scan_all
from .classifier import classify
from .watcher import LibraryWatcher, auto_optimize_new_games
from .searchlib import search_library
from .emuperf import apply_system_upgrades
from . import autostart as _autostart
from .applier import verify_fork_integrity

_SAMBOX = r"D:\Games\SAMBOX-Vfull"

# nome amigável de cada provedor na lista
_SOURCE_LABEL = {
    "sambox": "SAMBOX", "steam": "Steam", "xbox": "Game Pass",
    "epic": "Epic", "gog": "GOG", "custom": "Pasta",
}


class TurboPlayApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("TurboPlay")
        self.root.geometry("900x640")
        self.root.minsize(820, 580)
        self.games: list[dict] = []
        self.console_items: list[dict] = []
        self._build()
        threading.Thread(target=self._load_all, daemon=True).start()
        # watcher em tempo real: jogo novo → otimiza sozinho e recarrega lista
        self._watcher = LibraryWatcher(on_change=self._on_library_changed,
                                       poll_sec=20)
        threading.Thread(target=self._watcher.loop, daemon=True).start()

    # ---------- UI ----------
    def _build(self) -> None:
        header = tk.Frame(self.root, bg="#0b3d2e", height=58)
        header.pack(fill=tk.X)
        tk.Label(header, text="🎮 TurboPlay", font=("Segoe UI", 17, "bold"),
                 bg="#0b3d2e", fg="white").pack(side=tk.LEFT, padx=16, pady=8)
        tk.Label(header, text="biblioteca completa · otimizada automaticamente",
                 font=("Segoe UI", 10), bg="#0b3d2e", fg="#a8e6cf").pack(side=tk.LEFT, pady=14)

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 0))

        # aba 1: jogos nativos
        self.tab_native = tk.Frame(self.nb, bg="white")
        self.nb.add(self.tab_native, text="  🖥️  Meus Jogos (PC)  ")
        self._build_native_tab()

        # aba 2: consoles
        self.tab_console = tk.Frame(self.nb, bg="white")
        self.nb.add(self.tab_console, text="  🕹️  Consoles  ")
        self._build_console_tab()

        footer = tk.Frame(self.root)
        footer.pack(fill=tk.X, padx=10, pady=6)
        self.status = tk.Label(footer, text="Carregando biblioteca...",
                               font=("Segoe UI", 10), fg="#0b3d2e", anchor="w")
        self.status.pack(side=tk.LEFT)
        tk.Button(footer, text="↩ Reverter otimizações", font=("Segoe UI", 8),
                  bg="#dee2e6", relief="flat", command=self._on_rollback).pack(side=tk.RIGHT)
        # Início automático: atalho na pasta Inicializar do Windows, SEM usar a
        # chave Run — foi a Run key que disparou a heurística do Defender (D10).
        self.btn_auto = tk.Button(footer, text="…", font=("Segoe UI", 8),
                                  bg="#dee2e6", relief="flat", command=self._on_toggle_autostart)
        self.btn_auto.pack(side=tk.RIGHT, padx=(0, 6))
        self.root.after(200, self._refresh_autostart_btn)

    def _refresh_autostart_btn(self) -> None:
        on = _autostart.is_enabled()
        self.btn_auto.configure(text="⚙ Iniciar com o Windows: LIGADO" if on
                                else "⚙ Iniciar com o Windows: desligado")

    def _on_toggle_autostart(self) -> None:
        enable = not _autostart.is_enabled()
        if enable:
            ok = _autostart.set_enabled(True)
            self.status.configure(
                text="Atalho criado na pasta Inicializar — o TurboPlay passa a vigiar sozinho."
                if ok else "Não consegui criar o atalho.")
        else:
            ok = _autostart.set_enabled(False)
            self.status.configure(text="Autostart desligado." if ok
                                  else "Não consegui remover o atalho.")
        self._refresh_autostart_btn()

    def _on_library_changed(self) -> None:
        """Watcher detectou mudança: otimiza novos jogos e recarrega a GUI."""
        try:
            result = auto_optimize_new_games()
            for title, dec in result["applied"]:
                notify("TurboPlay", f"Novo jogo otimizado: {title} ({dec})")
            self.root.after(0, lambda: threading.Thread(
                target=self._load_all, daemon=True).start())
        except Exception:
            pass

    def _build_native_tab(self) -> None:
        top = tk.Frame(self.tab_native, bg="white")
        top.pack(fill=tk.X, padx=12, pady=8)
        self.btn_play = tk.Button(top, text="▶  JOGAR", width=16, height=2,
                                  font=("Segoe UI", 12, "bold"),
                                  bg="#0b8457", fg="white", relief="flat",
                                  state=tk.DISABLED, command=self._on_play_native)
        self.btn_play.pack(side=tk.LEFT, padx=(0, 12))
        self.lbl_native_info = tk.Label(top, text="Selecione um jogo e aperte JOGAR.\n✅ = otimizado (MFG/DLSS aplicado).",
                                        font=("Segoe UI", 9), fg="#333", justify=tk.LEFT, bg="white")
        self.lbl_native_info.pack(side=tk.LEFT)
        self.list_native = tk.Listbox(self.tab_native, font=("Segoe UI", 11),
                                      activestyle="none", selectbackground="#0b8457",
                                      selectforeground="white")
        self.list_native.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        self.list_native.bind("<Double-Button-1>", lambda e: self._on_play_native())

    def _build_console_tab(self) -> None:
        pane = tk.Frame(self.tab_console, bg="white")
        pane.pack(fill=tk.BOTH, expand=True)
        left = tk.Frame(pane, bg="white")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 4), pady=8)
        right = tk.Frame(pane, bg="white", width=280)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(4, 12), pady=8)
        right.pack_propagate(False)

        # 🔍 lupa de busca (nome, marca/console ou gênero)
        searchbar = tk.Frame(left, bg="white")
        searchbar.pack(fill=tk.X, pady=(0, 6))
        self.var_search = tk.StringVar()
        self.var_search.trace_add("write", lambda *_: self._on_search())
        ent = tk.Entry(searchbar, textvariable=self.var_search,
                       font=("Segoe UI", 11), relief="flat", bg="#f1f3f5")
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(0, 6))
        tk.Label(searchbar, text="🔍", font=("Segoe UI", 12), bg="white").pack(side=tk.LEFT)
        tk.Button(searchbar, text="✕", font=("Segoe UI", 9), relief="flat",
                  bg="#f1f3f5", command=lambda: self.var_search.set("")).pack(side=tk.LEFT, padx=4)

        self.list_console = tk.Listbox(left, font=("Segoe UI", 10),
                                       activestyle="none", selectbackground="#0b8457",
                                       selectforeground="white")
        self.list_console.pack(fill=tk.BOTH, expand=True)
        self.list_console.bind("<<ListboxSelect>>", self._on_console_select)
        self.list_console.bind("<Double-Button-1>", lambda e: self._on_play_console())

        tk.Label(right, text="🕹️ Console selecionado", font=("Segoe UI", 10, "bold"),
                 bg="white", fg="#0b3d2e").pack(anchor="w", pady=(0, 4))
        self.lbl_sys = tk.Label(right, text="", font=("Segoe UI", 9), bg="white",
                                justify=tk.LEFT, anchor="w", wraplength=250)
        self.lbl_sys.pack(anchor="w")
        tk.Label(right, text="✨ Melhorias disponíveis", font=("Segoe UI", 10, "bold"),
                 bg="white", fg="#0b3d2e").pack(anchor="w", pady=(14, 4))
        self.lbl_upgrades = tk.Label(right, text="", font=("Segoe UI", 9), bg="white",
                                     justify=tk.LEFT, anchor="w", wraplength=250)
        self.lbl_upgrades.pack(anchor="w")
        self.btn_play_c = tk.Button(right, text="▶  JOGAR", width=14, height=2,
                                    font=("Segoe UI", 12, "bold"),
                                    bg="#0b8457", fg="white", relief="flat",
                                    state=tk.DISABLED, command=self._on_play_console)
        self.btn_play_c.pack(anchor="w", pady=(16, 0))

    # ---------- dados ----------
    def _load_all(self) -> None:
        try:
            self.games = get_library()
            self.console_items = scan_console_library(__import__("pathlib").Path(_SAMBOX))
            stack_ok, stack_why = verify_fork_integrity()

            def render():
                self.list_native.delete(0, tk.END)
                for g in self.games:
                    mark = "🔒" if g.get("blocked") else ("✅" if g["optimized"] else "  ")
                    tag = _SOURCE_LABEL.get(g["source"], g["source"])
                    self.list_native.insert(tk.END, f" {mark}  {g['title']}   [{tag}]")
                self._render_console_list(self.console_items, "")

                pc = len(self.games)
                cons = len(self.console_items)
                nsys = len({i["system"] for i in self.console_items})
                opt = sum(1 for g in self.games if g["optimized"])
                blocked = sum(1 for g in self.games if g.get("blocked"))
                provs = " · ".join(
                    f"{_SOURCE_LABEL.get(k, k)} {v}"
                    for k, v in sorted(Counter(g["source"] for g in self.games).items()))
                msg = (f"{pc} jogo(s) PC ({provs or '—'}) · {opt} otimizado(s)"
                       f" · {cons} de console em {nsys} sistemas")
                if blocked:
                    msg += f" · {blocked} protegido(s) pela loja"
                msg += " · 100% reversível"
                self.status.configure(text=msg)
                if not stack_ok:
                    self.status.configure(
                        text="⚠ Stack DLSS5+MFG indisponível: " + stack_why)
                self.btn_play.configure(state=tk.NORMAL)
                self.btn_play_c.configure(state=tk.NORMAL)
            self.root.after(0, render)
        except Exception as e:
            self.root.after(0, lambda: self.status.configure(text=f"Erro: {e}"))

    def _render_console_list(self, items: list[dict], filter_desc: str) -> None:
        """Renderiza a lista agrupada por marca/console (ou resultados da busca)."""
        self.list_console.delete(0, tk.END)
        self._console_rows = []
        if filter_desc:
            self.list_console.insert(tk.END, f" 🔍  Resultados — {filter_desc}  ({len(items)} jogos)")
            self._console_rows.append(("header", None))
            # agrupa resultados por console pra ficar navegável
            by_sys: dict[str, list[dict]] = {}
            for it in items:
                by_sys.setdefault(it["system_name"], []).append(it)
            for name in sorted(by_sys):
                self.list_console.insert(tk.END, f" ▸ {name}  ({len(by_sys[name])})")
                self._console_rows.append(("header", None))
                for it in sorted(by_sys[name], key=lambda x: x["title"].lower()):
                    self.list_console.insert(tk.END, f"      • {it['title']}")
                    self._console_rows.append(("game", it))
            return
        by_sys: dict[str, list[dict]] = {}
        for it in items:
            by_sys.setdefault(f"{it['gen']:02d}|{it['system_name']}", []).append(it)
        for key in sorted(by_sys):
            gen_s, name = key.split("|", 1)
            first = by_sys[key][0]
            gen = f"G{gen_s}" if gen_s != "00" else "—"
            self.list_console.insert(tk.END, f" ▸ {name}  ({len(by_sys[key])} jogos)  [{gen}]  emu: {first['emu']}")
            self._console_rows.append(("header", None))
            for it in sorted(by_sys[key], key=lambda x: x["title"].lower()):
                self.list_console.insert(tk.END, f"      • {it['title']}")
                self._console_rows.append(("game", it))

    def _on_search(self) -> None:
        """Lupa: filtra em tempo real enquanto digita."""
        q = self.var_search.get().strip()
        if not q:
            self._render_console_list(self.console_items, "")
            return
        hits, desc = search_library(self.console_items, q)
        self._render_console_list(hits, f"{q!r} ({desc})" if hits else f"{q!r} — nada encontrado")

    # ---------- ações ----------
    def _on_play_native(self) -> None:
        sel = self.list_native.curselection()
        if not sel:
            self.status.configure(text="Selecione um jogo 👆")
            return
        g = self.games[sel[0]]
        self._play_flow(g["id"], g["title"], launch_path=g["launch_path"])

    def _on_play_console(self) -> None:
        sel = self.list_console.curselection()
        if not sel or self._console_rows[sel[0]][0] != "game":
            self.status.configure(text="Selecione um jogo (não o cabeçalho) 👆")
            return
        it = self._console_rows[sel[0]][1]
        self._play_flow(it["id"], it["title"], console_item=it)

    def _play_flow(self, gid: str, title: str, launch_path: str = "",
                   console_item: dict | None = None) -> None:
        self.status.configure(text=f"Preparando {title}...")
        def work():
            try:
                game_obj = None
                if console_item is None:
                    pre_launch({"id": gid})
                    game_obj = next((classify(c) for c in scan_all() if c.id == gid), None)
                    if game_obj:
                        popen, err = launch(game_obj)
                    else:
                        popen, err = None, "não encontrado"
                else:
                    if console_item.get("bat"):  # PC disfarçado de console
                        popen, err = None, ""
                        subprocess.Popen(["cmd", "/c", console_item["bat"]],
                                         creationflags=subprocess.CREATE_NO_WINDOW)
                    else:
                        # melhorias JIT do emulador (4K/PGXP etc.) antes de abrir
                        try:
                            ups = apply_system_upgrades(console_item["system"])
                            if ups:
                                self._log_safe(f"melhorias {console_item['system']}: {len(ups)} ajustes")
                        except Exception:
                            pass
                        popen, err = launch_emulated(
                            console_item["rom"], console_item["emu"], console_item["system"])
                if popen is None and err:
                    self.root.after(0, lambda: self.status.configure(
                        text=f"Não consegui abrir {title}: {err}"))
                    return
                self._log_safe(f"▶ {title} iniciado")
                self.root.after(0, lambda: self.status.configure(
                    text=f"{title} rodando — bom jogo! 🎮"))
                if console_item is None and game_obj:
                    post_launch_watch(game_obj, popen)
            except Exception as e:
                self.root.after(0, lambda: self.status.configure(text=f"Erro: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def _log_safe(self, msg: str) -> None:
        notify("TurboPlay", msg)

    def _on_console_select(self, _event=None) -> None:
        sel = self.list_console.curselection()
        if not sel or self._console_rows[sel[0]][0] != "game":
            return
        it = self._console_rows[sel[0]][1]
        self.lbl_sys.configure(
            text=f"{it['system_name']}\nGeração {it['gen'] or '—'} · emulador: {it['emu']}")
        ups = "\n".join(f"• {u}" for u in it["upgrades"]) or "• (padrão do emulador)"
        self.lbl_upgrades.configure(text=ups)

    def _on_rollback(self) -> None:
        def work():
            n = rollback_all()
            self.root.after(0, lambda: self.status.configure(
                text=f"{n} jogo(s) revertido(s)."))
            self.root.after(0, lambda: threading.Thread(
                target=self._load_all, daemon=True).start())
        threading.Thread(target=work, daemon=True).start()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    TurboPlayApp().run()


if __name__ == "__main__":
    main()
