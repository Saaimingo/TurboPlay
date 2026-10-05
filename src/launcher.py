"""TurboPlay — launcher: otimiza just-in-time, lança o jogo e verifica depois.

Fluxo do jogador: clica ▶ JOGAR →
  1. pré: garante otimização (aplica camadas se ainda não aplicou)
  2. lança o jogo (exe direto, steam:// ou .bat do SAMBOX)
  3. pós: quando o jogador fecha o jogo, lê os logs das camadas e notifica
"""
from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path

from .notify import notify
from .applier import _load_state, verify


def pre_launch(game_or_id) -> dict:
    """Garante otimização antes de abrir. Rápido (cache local)."""
    from .pipeline import optimize_one
    gid = game_or_id["id"] if isinstance(game_or_id, dict) else game_or_id
    return optimize_one(gid)


def _steam_exe() -> str:
    """steam.exe real. Sem isso, Steam em outro lugar nao é encontrado."""
    for p in (r"C:\Program Files (x86)\Steam\steam.exe",
              r"C:\Program Files\Steam\steam.exe"):
        if os.path.isfile(p):
            return p
    # tenta pelo proprio vaporlib do scan
    try:
        from .providers import steam_libraries
        for lib in steam_libraries():
            cand = Path(lib).parent.parent / "steam.exe"
            if cand.is_file():
                return str(cand)
    except Exception:
        pass
    return ""


def launch(game) -> tuple[subprocess.Popen | None, str]:
    """Lança o jogo pelo caminho mais apropriado.

    Devolve (processo, erro). O erro é VAZIO quando deu certo.

    Steam: usa `steam.exe -applaunch <appid>` em vez do protocolo `steam://`.
    Medido nesta máquina: o protocolo retorna sem erro e não abre nada; o
    -applaunch abre. Se nem o steam.exe for achado, cai para o exe direto
    (funciona para jogo sem DRM) e só ai o erro é reportado.
    """
    lp = game.launch_path or game.exe_path
    appid = getattr(game, "steam_appid", "")
    try:
        if appid and (game.source == "steam" or lp.lower().startswith("steam://")):
            exe = _steam_exe()
            if exe:
                subprocess.Popen([exe, "-applaunch", str(appid)],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
                return None, ""
            # sem steam.exe achado: tenta o proprio jogo (pode falhar em DRM)
            if os.path.isfile(game.exe_path):
                folder = os.path.dirname(game.exe_path)
                p = subprocess.Popen([game.exe_path], cwd=folder or None)
                return p, ""
            return None, "Steam nao encontrado e o executavel do jogo nao existe"
        if lp.lower().endswith(".bat"):
            folder = os.path.dirname(lp)
            p = subprocess.Popen(["cmd", "/c", lp], cwd=folder or None,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            return p, ""
        folder = os.path.dirname(lp)
        p = subprocess.Popen([lp], cwd=folder or None)
        return p, ""
    except OSError as e:
        return None, str(e)


def post_launch_watch(game, popen: subprocess.Popen | None) -> None:
    """Thread: espera o jogo fechar e verifica as camadas (toast)."""
    def work():
        try:
            if popen is not None:
                popen.wait()
            status = verify(game)
            if status == "MFG_NVIDIA_OK":
                notify("TurboPlay", f"{game.title}: frame generation NVIDIA ativa ✓")
            elif status == "OPTISCALER_OK":
                notify("TurboPlay", f"{game.title}: OptiScaler ativo ✓")
        except Exception:
            pass
    threading.Thread(target=work, daemon=True).start()
