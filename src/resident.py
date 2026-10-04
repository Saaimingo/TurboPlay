"""TurboPlay — modo residente: monitora e otimiza novos jogos automaticamente."""
from __future__ import annotations

import time
from pathlib import Path

from .applier import _load_state, _save_state, STATE_FILE
from .pipeline import run_full


def _state_sig() -> str:
    try:
        return f"{STATE_FILE.stat().st_mtime}:{STATE_FILE.stat().st_size}"
    except OSError:
        return "0:0"


def watch_loop(interval_sec: int = 1800, once: bool = False) -> None:
    """Roda o pipeline periodicamente (default: 30 min).

    Roda imediatamente na largada, depois dorme. Novos jogos detectados
    são otimizados na próxima passada.
    """
    from .notify import notify
    first = True
    while True:
        try:
            summary = run_full(auto_apply=True)
            if not first or once:
                pass
            if summary["summary"]["otimizados"]:
                notify(
                    "TurboPlay",
                    f"{summary['summary']['otimizados']} jogo(s) otimizado(s) automaticamente.",
                )
        except Exception as e:  # resiliente: nunca derruba o residente
            try:
                notify("TurboPlay", f"aviso: {e}")
            except Exception:
                pass
        if once:
            break
        first = False
        time.sleep(interval_sec)
