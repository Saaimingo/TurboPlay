"""TurboPlay — perfis de melhoria por emulador (aplica uma vez, com backup).

Escopo: o que cada emulador aceita por INI, seguro e reversível.
As melhorias "pesadas" (4K, PGXP, shaders) são as mesmas que o SAMBOX
oferece escondido — o TurboPlay as liga por padrão, sem o usuário saber.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

SAMBOX = Path(r"D:\Games\SAMBOX-Vfull\sistema\emulators")
BACKUP_DIR = Path.home() / "AppData" / "Local" / "TurboPlay" / "emulator_backups"

# sistema → (emulador, ajustes) — aplicados idempotentes
_PROFILES: dict[str, dict] = {
    # PS1: Duckstation — resolução 4K + PGXP (geometria 3D corrigida) + filtering
    "psx": {"emu": "duckstation", "ini": "settings.ini", "section": "GPU", "set": {
        "Renderer": "Vulkan",
        "ResolutionScale": "8",          # 8x = ~4K para PS1
        "PGXPEnable": "true",
        "PGXPCulling": "true",
        "PGXPTextureCorrection": "true",
        "TextureFiltering": "2",         # xBR
        "WireframeMode": "false",
        "ScaledDithering": "true",
    }},
    # PS2: PCSX2 — upscale 4K + filtering
    "ps2": {"emu": "pcsx2", "ini": "inis/GS.ini", "section": "EmuCore/GS", "set": {
        "upscale_multiplier": "6",
        "TextureFiltering": "2",
        "MaxAnisotropy": "8",
    }},
    # GC/Wii: Dolphin — 4K
    "gamecube": {"emu": "dolphin-emu", "ini": "Config/GFX.ini", "section": "Settings", "set": {
        "InternalResolution": "4",
        "Enhancements/ForceTextureFiltering": "true",
        "Enhancements/MaxAnisotropy": "8",
    }},
    "wii": {"emu": "dolphin-emu", "ini": "Config/GFX.ini", "section": "Settings", "set": {
        "InternalResolution": "4",
    }},
}

# RetroArch: shader CRT pra sistemas 2D + resolução alta (ASTC/xBR fica por conta do core)
_RA_SHADERS_2D = "shaders_slang/bezel/crt-easymode.slangp"  # existe no SAMBOX? conferir


def _backup(path: Path) -> None:
    bdir = BACKUP_DIR / path.parent.name
    bdir.mkdir(parents=True, exist_ok=True)
    dst = bdir / path.name
    if not dst.exists():
        shutil.copy2(path, dst)


def _set_ini_value(path: Path, section: str, key: str, value: str) -> bool:
    """Escreve key=value no INI (aceita seções 'A/B' → [A] + chave com barra)."""
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    # seções compostas ("EmuCore/GS") viram chave composta na seção raiz no PCSX2
    line_re = re.compile(rf"^{re.escape(key)}\s*=.*$", re.MULTILINE | re.IGNORECASE)
    new_line = f"{key}={value}"
    if line_re.search(text):
        text = line_re.sub(new_line, text, count=1)
    else:
        text += f"\n{new_line}\n"
    path.write_text(text, encoding="utf-8")
    return True


def apply_system_upgrades(system: str) -> list[str]:
    """Aplica as melhorias do sistema. Devolve lista do que foi feito."""
    profile = _PROFILES.get(system)
    done: list[str] = []
    if not profile:
        return done
    emu_dir = SAMBOX / profile["emu"]
    ini_path = emu_dir / profile["ini"]
    if not ini_path.exists():
        # duckstation/portable: settings.ini na raiz do emulador
        for cand in emu_dir.glob("*.ini"):
            ini_path = cand
            break
    if not ini_path.exists():
        return [f"INI não encontrado p/ {system} ({profile['emu']})"]
    _backup(ini_path)
    for k, v in profile["set"].items():
        if _set_ini_value(ini_path, profile["section"], k, v):
            done.append(f"{k}={v}")
    return done


def upgrades_status(system: str) -> str:
    """Estado legível das melhorias de um sistema (pra GUI)."""
    profile = _PROFILES.get(system)
    if not profile:
        return "padrão do emulador"
    return "otimizado ✓" if (SAMBOX / profile["emu"] / profile["ini"]).exists() else "disponível"
