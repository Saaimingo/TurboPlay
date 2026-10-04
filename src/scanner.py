"""TurboPlay — descoberta de jogos instalados (Steam, SAMBOX/RetroBat, pastas)."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from .models import Game

_EXE_BLACKLIST = {
    "unins000.exe", "uninstall.exe", "setup.exe", "crashreport.exe",
    "launcher.exe", "dxsetup.exe", "vcredist_x64.exe", "unitycrashhandler64.exe",
    "vc_redist.x64.exe", "dotnetfx45.exe", "oalinst.exe", "xinputd3d.exe",
}


def _game_id(exe: Path) -> str:
    h = hashlib.sha1(str(exe).lower().encode()).hexdigest()[:10]
    return f"tp_{h}"


def _title_from_folder(exe: Path) -> str:
    # nome da pasta-pai costuma ser o nome do jogo
    return exe.parent.name.replace("_", " ").strip()


def _steam_libraries() -> list[Path]:
    """Lê libraryfolders.vdf e devolve as bibliotecas Steam."""
    vdf = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    vdf = vdf / "Steam" / "steamapps" / "libraryfolders.vdf"
    libs: list[Path] = []
    if not vdf.exists():
        return libs
    text = vdf.read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(r'"path"\s+"([^"]+)"', text):
        p = Path(m.group(1).replace("\\\\", "\\"))
        if p.is_dir():
            libs.append(p / "steamapps" / "common")
    return libs


def _looks_like_game_exe(exe: Path) -> bool:
    name = exe.name.lower()
    if name in _EXE_BLACKLIST or name.startswith("unins"):
        return False
    if name.endswith(("_crack.exe", "-crack.exe")):
        return False
    try:
        size = exe.stat().st_size
    except OSError:
        return False
    # jogos reais são grandes; launchers/patchers costumam ser minúsculos
    return size > 5_000_000


def _steam_appids() -> dict[str, str]:
    """Mapa folder-name → appid lendo appmanifest_*.acf das bibliotecas."""
    out: dict[str, str] = {}
    for common in _steam_libraries():
        sa = common.parent
        if not sa.is_dir():
            continue
        for acf in sa.glob("appmanifest_*.acf"):
            try:
                text = acf.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            appid_m = re.search(r'"appid"\s+"(\d+)"', text)
            name_m = re.search(r'"installdir"\s+"([^"]+)"', text)
            if appid_m and name_m:
                out[name_m.group(1).lower()] = appid_m.group(1)
    return out


def scan_steam() -> list[Game]:
    games: list[Game] = []
    seen: set[str] = set()
    appids = _steam_appids()
    for common in _steam_libraries():
        if not common.is_dir():
            continue
        for folder in sorted(common.iterdir()):
            if not folder.is_dir():
                continue
            for exe in folder.glob("*.exe"):
                if _looks_like_game_exe(exe):
                    key = str(exe).lower()
                    if key not in seen:
                        seen.add(key)
                        appid = appids.get(folder.name.lower(), "")
                        games.append(Game(
                            id=_game_id(exe), title=_title_from_folder(exe),
                            exe_path=str(exe), folder=str(folder),
                            source="steam",
                            launch_path=f"steam://rungameid/{appid}" if appid else str(exe),
                            steam_appid=appid,
                        ))
                    break  # um por pasta Steam basta
    return games


_FRONTEND_EXES = {"retrobat.exe", "emulationstation.exe", "batgui.exe"}
_CD_RE = re.compile(r'cd(?:\s+/d)?\s+"?([^"]+?)"?\s*$', re.IGNORECASE)


def _parse_bat(path: Path) -> tuple[Path, str] | None:
    """Interpreta um .bat do RetroBat/SAMBOX.

    Devolve (pasta_resolvida_do_exe, nome_do_exe) ou None.
    Suporta `cd /d ".."` seguido de `start ... "Jogo.exe"` (caso RDR2).
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    cwd = path.parent
    result: tuple[Path, str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(("::", "REM", "@")) or not line:
            continue
        low = line.lower()
        if low.startswith("cd "):
            m = _CD_RE.match(line)
            if m:
                cwd = (cwd / m.group(1).strip()).resolve()
            continue
        if low.startswith("start "):
            exes = re.findall(r'"([^"]+\.exe)"', line, re.IGNORECASE)
            if exes:
                target = exes[-1]  # último = alvo (primeiro pode ser título)
                result = (cwd, target.strip('"'))
    return result


def scan_sambox(sambox_root: Path) -> list[Game]:
    """Varre roms/ de um SAMBOX/RetroBat atrás de jogos PC nativos via .bat."""
    games: list[Game] = []
    roms = sambox_root / "sistema" / "roms"
    if not roms.is_dir():  # estrutura RetroBat pura
        roms = sambox_root / "roms"
    if not roms.is_dir():
        return games
    for bat in roms.rglob("*.bat"):
        parsed = _parse_bat(bat)
        if not parsed:
            continue
        folder, exe_name = parsed
        exe = folder / exe_name
        if exe_name.lower() in _FRONTEND_EXES:
            continue
        # launchers pequenos (ex.: Launcher.exe do RDR2, 578KB) → pega o
        # maior exe da pasta do jogo (RDR2.exe, 89MB)
        if not exe.exists() or not _looks_like_game_exe(exe):
            big = [p for p in folder.glob("*.exe") if _looks_like_game_exe(p)]
            if not big:
                continue
            exe = max(big, key=lambda p: p.stat().st_size)
        games.append(Game(
            id=_game_id(exe), title=bat.stem, exe_path=str(exe),
            folder=str(exe.parent), source="sambox",
            launch_path=str(bat),  # jogador joga via .bat (mantém mínimo do RetroBat)
        ))
    return games


def scan_all(sambox_roots: list[Path] | None = None) -> list[Game]:
    games: list[Game] = []
    games.extend(scan_steam())
    for root in (sambox_roots or [Path(r"D:\Games\SAMBOX-Vfull")]):
        games.extend(scan_sambox(root))
    # dedup por exe
    seen: set[str] = set()
    unique: list[Game] = []
    for g in games:
        key = g.exe_path.lower()
        if key not in seen:
            seen.add(key)
            unique.append(g)
    return unique
