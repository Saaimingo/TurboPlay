"""TurboPlay — descoberta de jogos em QUALQUER provedor.

Cada provedor devolve `Game` com `source` próprio. O princípio é o mesmo do
resto do projeto: sem dependências, só stdlib, e honestidade radical sobre o
que é ou não é possível fazer.

REGRA DE OURO DESTE ARQUIVO
--------------------------
Um jogo que não pode ser modificado é marcado `protected_install=True` e o
pipeline devolve NOOP com o motivo. Isso vale em especial para Game Pass /
Microsoft Store: as pastas são pacotes MSIX assinados dentro de
`C:\\Program Files\\WindowsApps`, com ACL do TrustedInstaller. Injetar DLL ali
quebra a assinatura do pacote e o jogo simplesmente deixa de abrir. Detectar e
avisar é a única conduta correta — prometer "otimizado" seria mentira.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import Path

from .models import Game

# ── utilidades ────────────────────────────────────────────────────────────────


def game_id(path: str, prefix: str = "tp") -> str:
    """ID estável por caminho (mesmo jogo = mesmo ID entre execuções)."""
    return f"{prefix}_{hashlib.sha1(str(path).lower().encode()).hexdigest()[:10]}"


def is_writable(folder: str) -> bool:
    """A pasta aceita escrita DE VERDADE? Testa criando e apagando um arquivo.

    Usa um nome temporário exclusivo para nunca sobrescrever/remover arquivo alheio.
    Não confiar em ACL nem em is_admin(): a resposta real é tentar gravar.
    """
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="ascii", prefix=".tp_write_probe_",
                suffix=".tmp", dir=folder, delete=True) as probe:
            probe.write("x")
        return True
    except OSError:
        return False


# ── Steam ─────────────────────────────────────────────────────────────────────


def steam_libraries() -> list[Path]:
    """Bibliotecas Steam via libraryfolders.vdf (caminho real, não presumido)."""
    base = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    vdf = base / "Steam" / "steamapps" / "libraryfolders.vdf"
    if not vdf.exists():
        return []
    libs: list[Path] = []
    text = vdf.read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(r'"path"\s+"([^"]+)"', text):
        p = Path(m.group(1).replace("\\\\", "\\"))
        if p.is_dir():
            libs.append(p / "steamapps" / "common")
    return libs


def scan_steam() -> list[Game]:
    """Jogos Steam: 1 por pasta, usando o appid do manifest pra launcher."""
    if not steam_libraries():
        return []
    appids: dict[str, str] = {}
    for common in steam_libraries():
        for acf in (common.parent).glob("appmanifest_*.acf"):
            try:
                text = acf.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            a = re.search(r'"appid"\s+"(\d+)"', text)
            d = re.search(r'"installdir"\s+"([^"]+)"', text)
            if a and d:
                appids[d.group(1).lower()] = a.group(1)

    from .scanner import _looks_like_game_exe

    games: list[Game] = []
    seen: set[str] = set()
    for common in steam_libraries():
        if not common.is_dir():
            continue
        for folder in sorted(common.iterdir()):
            if not folder.is_dir():
                continue
            cands = [e for e in folder.glob("*.exe") if _looks_like_game_exe(e)]
            if not cands:
                continue
            # o exe maior é quase sempre o jogo (launchers são pequenos)
            exe = max(cands, key=lambda p: p.stat().st_size)
            key = str(exe).lower()
            if key in seen:
                continue
            seen.add(key)
            appid = appids.get(folder.name.lower(), "")
            games.append(Game(
                id=game_id(str(exe)), title=folder.name.replace("_", " "),
                exe_path=str(exe), folder=str(folder), source="steam",
                launch_path=f"steam://rungameid/{appid}" if appid else str(exe),
                steam_appid=appid,
                writable=is_writable(str(folder)),
            ))
    return games


# ── Xbox / Game Pass Ultimate (Microsoft Store, MSIX) ────────────────────────

_XBOX_ROOTS = [
    Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft" / "GameConfig",
]


def scan_xbox() -> list[Game]:
    """Game Pass Ultimate / MS Store — detecta e marca como PROTEGIDO.

    Os jogos MSIX vivem em `C:\\Program Files\\WindowsApps`, com ACL do
    TrustedInstaller e assinatura de pacote. Injetar DLL não é suportável:
    o pacote deixa de validar e o jogo não abre. Por isso `protected_install`.

    A lista vem do GameConfig (XML do launcher da Store), que é legível sem
    privilégios; o WindowsApps em si normalmente não é.
    """
    games: list[Game] = []
    seen: set[str] = set()
    for root in _XBOX_ROOTS:
        if not root.is_dir():
            continue
        for xml in root.glob("*.xml"):
            try:
                text = xml.read_text(encoding="utf-16-le", errors="ignore")
                if "<Game" not in text:
                    text = xml.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            # <Game installFolder="C:\...\WindowsApps\X" ... />
            for m in re.finditer(r'installFolder="([^"]+)"', text):
                folder = Path(m.group(1))
                if not folder.is_dir() or str(folder).lower() in seen:
                    continue
                exes = [e for e in folder.glob("*.exe")
                        if e.stat().st_size > 5_000_000] if _safe_listdir(folder) else []
                if not exes:
                    continue
                exe = max(exes, key=lambda p: p.stat().st_size)
                seen.add(str(folder).lower())
                games.append(Game(
                    id=game_id(str(exe)), title=folder.name,
                    exe_path=str(exe), folder=str(folder), source="xbox",
                    launch_path=str(exe),
                    protected_install=True, writable=False,
                    blocked_reason=("pacote MSIX/Store assinado em WindowsApps — "
                                    "injeção quebraria a assinatura; otimização não aplicável"),
                ))
    return games


def _safe_listdir(folder: Path) -> bool:
    try:
        next(iter(folder.iterdir()), None)
        return True
    except OSError:
        return False


# ── Epic / GOG ───────────────────────────────────────────────────────────────


def scan_epic() -> list[Game]:
    """Epic Games: registro deVAS/ launcher_installed + pastas de jogos."""
    games: list[Game] = []
    for base in _epic_roots():
        for folder in base.iterdir() if base.is_dir() else []:
            if not folder.is_dir():
                continue
            _collect_generic(folder, "epic", games)
    return games


def _epic_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        out = subprocess.run(
            ["reg", "query", r"HKLM\SOFTWARE\WOW6432Node\Epic Games",
             "/s", "/f", "Location", "/v", "/t", "REG_SZ"],
            capture_output=True, text=True, encoding="mbcs", errors="replace",
            timeout=10)
        for line in out.stdout.splitlines():
            m = re.search(r"REG_SZ\s+(.+?)\s*$", line)
            if m:
                roots.append(Path(m.group(1).strip()))
    except (OSError, subprocess.SubprocessError):
        pass
    roots.append(Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Epic" / "EpicGamesLauncher")
    return roots


def scan_gog() -> list[Game]:
    """GOG Galaxy: pastas de jogos são as subpastas diretas de library path."""
    games: list[Game] = []
    bases = [Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "GOG.com" / "Games"]
    for base in bases:
        if not base.is_dir():
            continue
        for folder in base.iterdir():
            if folder.is_dir():
                _collect_generic(folder, "gog", games)
    return games


# ── Pastas custom (qualquer lugar) ────────────────────────────────────────────

_CUSTOM_FILES = Path.home() / "AppData" / "Local" / "TurboPlay" / "custom_folders.txt"


def custom_folders() -> list[Path]:
    """Pastas que o usuário mandou varrer. Arquivo opcional, uma linha por pasta.

    É a rede de segurança: qualquer jogo fora de Steam/Store/Epic/GOG/SAMBOX
    entra por aqui.
    """
    if not _CUSTOM_FILES.exists():
        return []
    out: list[Path] = []
    for line in _CUSTOM_FILES.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            p = Path(line)
            if p.is_dir():
                out.append(p)
    return out


def _collect_generic(folder: Path, source: str, out: list[Game]) -> None:
    """Heurística genérica: acha o maior .exe da subpasta = jogo."""
    from .scanner import _looks_like_game_exe
    exes = [e for e in folder.glob("*.exe") if _looks_like_game_exe(e)]
    if not exes:
        for sub in sorted(folder.iterdir()) if _safe_listdir(folder) else []:
            if sub.is_dir():
                exes = [e for e in sub.glob("*.exe") if _looks_like_game_exe(e)]
                if exes:
                    folder = sub
                    break
    if not exes:
        return
    exe = max(exes, key=lambda p: p.stat().st_size)
    out.append(Game(
        id=game_id(str(exe)), title=folder.name.replace("_", " "),
        exe_path=str(exe), folder=str(exe.parent), source=source,
        launch_path=str(exe), writable=is_writable(str(exe.parent)),
    ))


def scan_custom() -> list[Game]:
    games: list[Game] = []
    for base in custom_folders():
        for folder in sorted(base.iterdir()) if _safe_listdir(base) else []:
            if folder.is_dir():
                _collect_generic(folder, "custom", games)
    return games


# ── anti-spoofing: o scanner NÃO deve tratar ferramenta como jogo ────────────

_NOT_A_GAME_EXES = {
    "duckstation-qt-x64-releaseltcg.exe", "dolphin-emu-nogui.exe", "cemu.exe",
    "rpcs3.exe", "yuzu.exe", "ryujinx.exe", "pcsx2-qt.exe", "pcsx2.exe",
    "retroarch.exe", "mesen.exe", "mupen64plus-next.exe", "flycast.exe",
    "melonds.exe", "citra.exe", "stella.exe", "mednafen.exe", "bizhawk.exe",
    "ppsspp.exe", "xa.exe", "nestopia.exe", "snes9x.exe",
}


def is_tool_exe(exe_path: str) -> bool:
    """Executável conhecido de emulador/frontend — nunca é jogo pra otimizar."""
    name = Path(exe_path).name.lower()
    return name in _NOT_A_GAME_EXES


# ── agregação ────────────────────────────────────────────────────────────────


def scan_all(sambox_roots: list[Path] | None = None,
             extra_custom: list[Path] | None = None) -> list[Game]:
    """Todos os provedores, deduplicado por executável."""
    from .scanner import scan_sambox

    games: list[Game] = []
    games.extend(scan_steam())
    games.extend(scan_xbox())
    games.extend(scan_epic())
    games.extend(scan_gog())
    for root in (sambox_roots or [Path(r"D:\Games\SAMBOX-Vfull")]):
        games.extend(scan_sambox(root))
    games.extend(scan_custom())
    for folder in (extra_custom or []):
        if Path(folder).is_dir():
            _collect_generic(Path(folder), "custom", games)

    seen: set[str] = set()
    unique: list[Game] = []
    for g in games:
        if is_tool_exe(g.exe_path):
            continue          # emulador/frontend nunca entra na fila
        key = g.exe_path.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(g)
    return unique


def provider_summary(games: list[Game]) -> dict[str, int]:
    """Contagem por provedor — para a GUI dizer o que ele enxergou."""
    out: dict[str, int] = {}
    for g in games:
        out[g.source] = out.get(g.source, 0) + 1
    return dict(sorted(out.items()))