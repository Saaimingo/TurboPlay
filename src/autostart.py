"""TurboPlay — autostart no logon do Windows, SEM usar a chave Run.

Por que não a chave Run (decisão D10, 21/09/2026):
O Defender classificou o conjunto "exe sem assinatura + atalho + chave Run"
como comportamento de malware e quarantenou o executável DUAS vezes. A Run key
era o gatilho da heurística. Desde então o produto roda sem persistência no
registro.

A alternativa adotada aqui é a pasta **Startup** com um atalho .lnk apontando
para `TurboPlay.exe watch --silent`. É a via suportada pelo Windows, não toca o
registro e não acopla exe a persistência — que era exatamente o gatilho.

Mesma interface pública de antes (`is_enabled`/`set_enabled`), então a GUI não
precisa mudar. Mas o botão não se chama mais "Auto no boot" e avisa que é
opcional e reversível.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_LINK_NAME = "TurboPlay.lnk"


def _exe_path() -> str:
    """Caminho do exe real; string vazia se não houver um .exe válido.

    Nunca apontar atalho para caminho que não existe (bug anterior gravava
    "...\\TurboPlay\\-c" quando rodava via `python -c`).
    """
    if getattr(sys, "frozen", False):
        p = os.path.abspath(sys.executable)
    else:
        p = os.path.abspath(sys.argv[0])
    if p.lower().endswith(".exe") and os.path.isfile(p):
        return p
    return ""


def startup_dir() -> Path:
    """Pasta Startup do usuário atual (roaming)."""
    appdata = os.environ.get("APPDATA", "")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _link_path() -> Path:
    return startup_dir() / _LINK_NAME


def _install_root() -> Path | None:
    """Onde o exe realmente está (%LOCALAPPDATA%\\TurboPlay\\app)."""
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "TurboPlay" / "app" / "TurboPlay.exe"
    if local.is_file():
        return local
    return None


def is_enabled() -> bool:
    """O atalho de autostart existe?"""
    return _link_path().is_file()


def status_detail() -> str:
    """Texto honesto pro jogador — nunca promete o que não faz."""
    if not is_enabled():
        return "desligado (o TurboPlay só age com a janela aberta)"
    return "ligado (atalho na pasta Inicializar do Windows)"


def set_enabled(enable: bool) -> bool:
    """Cria/remove o atalho de autostart. Devolve sucesso."""
    link = _link_path()
    try:
        if not enable:
            if link.exists():
                link.unlink()
            return True
        exe = _install_root() or (_exe_path() or None)
        if not exe:
            return False
        link.parent.mkdir(parents=True, exist_ok=True)
        # PowerShell faz o .lnk; sem registro, sem serviço.
        ps = (
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{link}');"
            "$s.TargetPath='{exe}';"
            "$s.Arguments='watch --silent';"
            "$s.WorkingDirectory='{wd}';"
            "$s.WindowStyle=7;"
            "$s.Description='TurboPlay — otimizacao automatica de jogos';"
            "$s.Save()"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=20)
        return out.returncode == 0 and link.is_file()
    except (OSError, subprocess.SubprocessError):
        return False