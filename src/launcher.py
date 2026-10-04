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

from .notify import notify
from .applier import _load_state, verify


def pre_launch(game_or_id) -> dict:
    """Garante otimização antes de abrir. Rápido (cache local)."""
    from .pipeline import optimize_one
    gid = game_or_id["id"] if isinstance(game_or_id, dict) else game_or_id
    return optimize_one(gid)


def launch(game) -> tuple[subprocess.Popen | None, str]:
    """Lança o jogo pelo caminho mais apropriado."""
    lp = game.launch_path or game.exe_path
    folder = os.path.dirname(lp)
    try:
        if lp.lower().endswith(".bat"):
            p = subprocess.Popen(["cmd", "/c", lp], cwd=folder,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        elif game.source == "steam" and getattr(game, "steam_appid", ""):
            # respeita DRM/overlay da Steam
            subprocess.Popen(["cmd", "/c", f'start "" "steam://rungameid/{game.steam_appid}"'],
                             creationflags=subprocess.CREATE_NO_WINDOW)
            p = None
        else:
            p = subprocess.Popen([lp], cwd=folder)
        return p, lp
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
