"""TurboPlay — camada DLSS Enabler (a ponte de FG pra jogos sem FG nativa).

Aprendizado da sessão 21/09 (validado no RDR2):
- O Enabler distribui SOMENTE pelo Nexus (login manual). Pacote local = zip
  colocado em _downloads/dlss-enabler/ pelo titular.
- O zip contém um único `version.dll` (auto-extrator: descomprime os runtimes
  NVIDIA na primeira execução do jogo).
- Slot de hook: instalamos como **dxgi.dll** (renomear é oficialmente
  documentado pelo autor, ex.: instrução para RE9). O slot version.dll
  fica para o proxy SM86 (o jogo importa version.dll; ambos os proxies
  têm tabela de forward — renomear entre nomes de sistema é seguro para o
  Enabler, NÃO para o SM86, cujo release só traz a variante version.dll).
- O Enabler embute o OptiScaler 0.9.5-pre3 → o OptiScaler standalone
  (winmm.dll, 0.9.4) torna-se REDUNDANTE e é removido na instalação
  (com backup .tp-bak2) para evitar dois OptiScalers no mesmo processo.
- Config de FG do jogo não muda: continuamos usando os overrides do perfil
  (FGInput=upscaler / FGOutput=fsrfg) via optiscaler.ini do Enabler.

Se não houver pacote local, a camada é pulada (não-bloqueante): o jogo fica
com OptiScaler+SM86 e FG FSR3 2x — upgrade posterior quando o zip aparecer.
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from .applier import _backup, _load_state, _save_state

# locais onde o titular pode ter colocado o zip do Nexus (ou extraído)
_SEARCH_PATHS = [
    Path(r"D:\Games\MFG-NVIDIA-DLSS5\_downloads\dlss-enabler"),
]

# OptiScaler standalone fica redundante quando o Enabler entra (ele embute o próprio)
_REDUNDANT = ["winmm.dll", "OptiScaler.ini"]


def _find_package() -> Path | None:
    """Acha o zip (ou version.dll já extraído) do Enabler."""
    for base in _SEARCH_PATHS:
        if not base.is_dir():
            continue
        # 1) dll já extraída
        for cand in sorted(base.rglob("version.dll")):
            return cand
        # 2) zip do Nexus (nome variável: "DLSS Enabler ... .zip")
        for z in sorted(base.glob("*.zip")):
            return z
    return None


def try_install_enabler(game) -> tuple[bool, str]:
    """Instala DLSS Enabler como dxgi.dll a partir de pacote local.

    Não-bloqueante: sem pacote, retorna False com motivo e o jogo segue
    com a rota OptiScaler+SM86 (FSR3-FG).
    """
    folder = Path(game.folder)
    pkg = _find_package()
    if pkg is None:
        return False, "DLSS Enabler: pacote local ausente (baixar no Nexus) — camada pulada"

    # backup dos arquivos que vamos tocar (inclui o que será removido)
    _backup(game, ["dxgi.dll", "OptiScaler.ini", "winmm.dll"])

    src_dll: Path | None
    if pkg.suffix.lower() == ".zip":
        extract_dir = pkg.parent / f"_extracted_{pkg.stem[:24]}"
        try:
            with zipfile.ZipFile(pkg) as zf:
                zf.extractall(extract_dir)
        except zipfile.BadZipFile:
            return False, "DLSS Enabler: zip corrompido — baixar novamente no Nexus"
        candidates = list(extract_dir.rglob("version.dll")) + \
            list(extract_dir.rglob("dlss-enabler.dll"))
        if not candidates:
            return False, "DLSS Enabler: zip sem version.dll esperado — revisar pacote"
        src_dll = candidates[0]
    else:
        src_dll = pkg

    shutil.copy2(src_dll, folder / "dxgi.dll")

    # remove OptiScaler standalone redundante (Enabler embute o próprio)
    removed = []
    for name in _REDUNDANT:
        f = folder / name
        if f.exists():
            f.unlink()
            removed.append(name)

    # registrar no state p/ rollback correto
    state = _load_state()
    entry = state.get(game.id, {})
    inst = set(entry.get("installed_files", []))
    inst.update(["dxgi.dll"])
    entry["installed_files"] = sorted(inst)
    entry["enabler"] = True
    state[game.id] = entry
    _save_state(state)

    msg = "DLSS Enabler ✓ (dxgi.dll, OptiScaler embutido 0.9.5)"
    if removed:
        msg += f" — OptiScaler standalone removido: {', '.join(removed)}"
    return True, msg
