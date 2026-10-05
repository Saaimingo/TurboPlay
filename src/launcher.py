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
    """Lança o jogo pelo caminho mais apropriado.

    Devolve (processo, erro). O erro é VAZIO quando deu certo — inclusive no
    caso Steam, que não dá para pegar o Popen porque quem abre é o próprio
    cliente. Antes esta função devolvia a URL como erro e a GUI acusava falha
    mesmo com o jogo abrindo.
    """
    lp = game.launch_path or game.exe_path
    try:
        if lp.lower().startswith("steam://") or (
                game.source == "steam" and getattr(game, "steam_appid", "")):
            # respeita DRM/overlay da Steam. os.startfile usa a associacao do
            # protocolo registered; `cmd /c start` com URL quebrava e o
            # Windows reclamava de "\\".
            url = (lp if lp.lower().startswith("steam://")
                   else f"steam://rungameid/{game.steam_appid}")
            os.startfile(url)
            return None, ""
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
