"""TurboPlay — lançamento de jogos emulados (CLI específica de cada emulador)."""
from __future__ import annotations

import subprocess
from pathlib import Path

# emulador → (exe relativo, template de args; {rom} = caminho da rom)
_EMU_TEMPLATES: dict[str, dict] = {
    "duckstation":  {"exe": "duckstation-qt-x64-ReleaseLTCG.exe", "args": ["-nogui", "{rom}"]},
    "pcsx2":        {"exe": "pcsx2-qt.exe", "args": ["-nogui", "{rom}"]},
    "pcsx2-16":     {"exe": "pcsx2.exe", "args": ["{rom}"]},
    "rpcs3":        {"exe": "rpcs3.exe", "args": ["{rom}"]},
    "ppsspp":       {"exe": "PPSSPPWindows64.exe", "args": ["{rom}"]},
    "vita3k":       {"exe": "Vita3K.exe", "args": ["{rom}"]},
    "dolphin-emu":  {"exe": "Dolphin.exe", "args": ["-b", "-e", "{rom}"]},
    "cemu":         {"exe": "Cemu.exe", "args": ["-g", "{rom}", "-f"]},
    "citra":        {"exe": "citra-qt.exe", "args": ["{rom}"]},
    "melonds":      {"exe": "melonDS.exe", "args": ["{rom}"]},
    "mgba":         {"exe": "mgba-qt.exe", "args": ["{rom}"]},
    "mupen64":      {"exe": "mupen64plus-ui-console.exe", "args": ["--nogui", "{rom}"]},
    "simple64":     {"exe": "simple64-gui.exe", "args": ["{rom}"]},
    "flycast":      {"exe": "flycast.exe", "args": ["{rom}"]},
    "redream":      {"exe": "redream.exe", "args": ["{rom}"]},
    "xemu":         {"exe": "xemu.exe", "args": ["-dvd_path", "{rom}"]},
    "xenia":        {"exe": "xenia.exe", "args": ["{rom}"]},
    "xenia-canary": {"exe": "xenia_canary.exe", "args": ["{rom}"]},
    "shadps4":      {"exe": "shadPS4.exe", "args": ["{rom}"]},
    "ryujinx":      {"exe": "Ryujinx.exe", "args": ["{rom}"]},
    "yuzu":         {"exe": "yuzu.exe", "args": ["-g", "{rom}"]},
    "suyu":         {"exe": "suyu.exe", "args": ["-g", "{rom}"]},
    "sudachi":      {"exe": "sudachi.exe", "args": ["-g", "{rom}"]},
    "lime3ds":      {"exe": "lime3ds.exe", "args": ["{rom}"]},
    "mandarine":    {"exe": "mandarine.exe", "args": ["{rom}"]},
    "scummvm":      {"exe": "scummvm.exe", "args": ["{rom}"]},
    "dosbox":       {"exe": "dosbox.exe", "args": ["{rom}"]},
    "supermodel":   {"exe": "Supermodel.exe", "args": ["{rom}"]},
    "demul":        {"exe": "demul.exe", "args": ["-run={rom}"]},
    "mame":         {"exe": "mame.exe", "args": ["{rom}"]},
    "fbneo":        {"exe": "fbneo.exe", "args": ["{rom}"]},
    "mednafen":     {"exe": "mednafen.exe", "args": ["{rom}"]},
    "stella":       {"exe": "stella64.exe", "args": ["{rom}"]},
    "snes9x":       {"exe": "snes9x-x64.exe", "args": ["{rom}"]},
    "bizhawk":      {"exe": "EmuHawk.exe", "args": ["{rom}"]},
    "ares":         {"exe": "ares.exe", "args": ["{rom}"]},
    "beetle-psx":   {"exe": "mednafen.exe", "args": ["{rom}"]},
}

# fallback universal: RetroArch com libretro cores por sistema
_RETROARCH_CORES = {  # nomes confirmados na pasta cores/ do SAMBOX
    "nes": "nestopia_libretro.dll", "snes": "snes9x_libretro.dll",
    "gb": "gambatte_libretro.dll", "gbc": "gambatte_libretro.dll",
    "gba": "mgba_libretro.dll", "mastersystem": "genesis_plus_gx_libretro.dll",
    "megadrive": "genesis_plus_gx_libretro.dll", "segacd": "genesis_plus_gx_libretro.dll",
    "sega32x": "picodrive_libretro.dll", "saturn": "mednafen_saturn_libretro.dll",
    "psx": "mednafen_psx_hw_libretro.dll", "pcengine": "mednafen_pce_fast_libretro.dll",
    "neogeo": "fbneo_libretro.dll", "arcade": "fbneo_libretro.dll",
    "n64": "mupen64plus_next_libretro.dll", "dreamcast": "flycast_libretro.dll",
    "virtualboy": "mednafen_vb_libretro.dll", "atarist": "atarist_libretro.dll",
    "psp": "ppsspp_libretro.dll", "nds": "melonds_libretro.dll",
    "gamecube": "dolphin_libretro.dll", "wii": "dolphin_libretro.dll",
    "3ds": "citra_libretro.dll", "atari2600": "stella_libretro.dll",
}


_EXE_FALLBACKS = {  # candidatos em ordem: o que existir é usado
    "duckstation": ["duckstation-qt-x64-ReleaseLTCG.exe", "duckstation-qt.exe"],
    "pcsx2": ["pcsx2-qt.exe", "pcsx2.exe"],
    "dolphin-emu": ["Dolphin.exe"],
    "citra": ["citra-qt.exe"],
    "yuzu": ["yuzu.exe"],
}


def _find_emu_exe(emu_dir: Path, emu: str) -> Path | None:
    """Acha o exe do emulador: template → fallbacks → maior exe da pasta."""
    tpl = _EMU_TEMPLATES.get(emu)
    if tpl:
        cand = emu_dir / tpl["exe"]
        if cand.exists():
            return cand
    for name in _EXE_FALLBACKS.get(emu, []):
        cand = emu_dir / name
        if cand.exists():
            return cand
    exes = [p for p in emu_dir.glob("*.exe") if not p.name.lower().startswith(("updater", "unins"))]
    if exes:
        return max(exes, key=lambda p: p.stat().st_size)
    return None


def launch_emulated(rom: str, emu: str, system: str) -> tuple[subprocess.Popen | None, str]:
    """Lança uma rom. Ordem:

    1. RetroArch direto + core libretro confirmado, com cwd NA PASTA DO
       retroarch (crítico: o retroarch.cfg do SAMBOX usa caminhos relativos
       tipo ":\cores" que só resolvem com o cwd certo) — testado OK:
       Nestopia abriu 1942 (NES) com esse caminho.
    2. Emulador dedicado (Duckstation, PCSX2, Dolphin...).
    3. RetroArch genérico (resolve core pela extensão).
    """
    sambox_root = Path(r"D:\Games\SAMBOX-Vfull")
    sambox = sambox_root / "sistema" / "emulators"
    ra = sambox / "retroarch" / "retroarch.exe"
    # sistemas que vivem no RetroArch (2D/clássicos) vão SEMPRE por RetroArch
    # direto — é a rota testada e mais leve
    if ra.exists() and system in _RETROARCH_CORES:
        core = _RETROARCH_CORES[system]
        core_path = sambox / "retroarch" / "cores" / core
        if core_path.exists():
            try:
                return subprocess.Popen(
                    [str(ra), "-L", str(core_path), rom],
                    cwd=str(ra.parent)), ""
            except OSError as e:
                return None, str(e)
    emu_dir = sambox / emu
    if emu_dir.is_dir() and emu != "retroarch":
        exe = _find_emu_exe(emu_dir, emu)
        if exe:
            tpl = _EMU_TEMPLATES.get(emu)
            args_tpl = tpl["args"] if tpl else ["{rom}"]
            args = [str(exe)] + [a.replace("{rom}", rom) for a in args_tpl]
            try:
                return subprocess.Popen(args, cwd=str(exe.parent)), ""
            except OSError as e:
                return None, str(e)
    if ra.exists():
        try:
            return subprocess.Popen([str(ra), rom], cwd=str(ra.parent)), ""
        except OSError as e:
            return None, str(e)
    return None, f"emulador não encontrado: {emu}"
