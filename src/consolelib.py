"""TurboPlay — biblioteca de consoles: varre roms/ do SAMBOX e classifica cada
jogo pelo sistema (console), resolvendo o emulador e as melhorias disponíveis.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from .systems import ROM_EXTS, system_info

_GAME_NAME_CLEAN = re.compile(r"[\(\[\{].*?[\)\]\}]")


def _game_id(rom: Path) -> str:
    h = hashlib.sha1(str(rom).lower().encode()).hexdigest()[:10]
    return f"tc_{h}"


def _clean_title(stem: str) -> str:
    t = _GAME_NAME_CLEAN.sub("", stem)
    t = re.sub(r"[_.]", " ", t)
    return re.sub(r"\s+", " ", t).strip() or stem


def _gamelist_map(system_dir: Path) -> dict[str, dict]:
    """Lê gamelist.xml do RetroBat (nome, capa, descrição) por rom."""
    out: dict[str, dict] = {}
    gl = system_dir / "gamelist.xml"
    if not gl.exists():
        return out
    try:
        root = ET.parse(gl).getroot()
    except ET.ParseError:
        return out
    for game in root.iter("game"):
        path = game.findtext("path", "").strip()
        if not path:
            continue
        rom_name = Path(path).name.lower()
        out[rom_name] = {
            "name": game.findtext("name", "").strip(),
            "image": game.findtext("image", "").strip(),
            "desc": game.findtext("desc", "").strip()[:120],
        }
    return out


def scan_console_library(sambox_root: Path, max_per_system: int = 200) -> list[dict]:
    """Devolve a biblioteca de jogos emulados agrupada por console.

    Cada item: {id, title, system, system_name, gen, emu, rom, bat, upgrades}
    """
    roms_root = sambox_root / "sistema" / "roms"
    if not roms_root.is_dir():
        roms_root = sambox_root / "roms"
    if not roms_root.is_dir():
        return []
    items: list[dict] = []
    for system_dir in sorted(roms_root.iterdir()):
        if not system_dir.is_dir() or system_dir.name.startswith((".", "$")):
            continue
        sid = system_dir.name.lower()
        if sid in {"downloads", "bezels", "images", "videos", "manuals",
                   "media", "wheel", "snapshots", "screenshots", "saves"}:
            continue
        info = system_info(sid)
        meta = _gamelist_map(system_dir)
        count = 0
        # .bat primeiro (jogos PC disfarçados de console, ex. ps5/RDR2)
        bats = list(system_dir.rglob("*.bat"))
        for bat in bats:
            if bat.name.lower().startswith(("force ", "launcher")):
                continue
            count += 1
            items.append({
                "id": _game_id(bat), "title": _clean_title(bat.stem),
                "system": sid, "system_name": info["name"], "gen": info["gen"],
                "emu": "PC nativo", "rom": "", "bat": str(bat),
                "image": "", "upgrades": info["upgrades"],
                "native_pc": True,
            })
            if count >= max_per_system:
                break
        if count:
            continue  # sistema com jogos PC nativos não precisa listar roms
        for rom in sorted(system_dir.rglob("*")):
            if not rom.is_file() or rom.suffix.lower() not in ROM_EXTS:
                continue
            if rom.name.lower() in meta:
                m = meta[rom.name.lower()]
                title = m["name"] or _clean_title(rom.stem)
                image = m["image"]
            else:
                title, image = _clean_title(rom.stem), ""
            rel_img = (system_dir / image.replace("~", ".")) if image.startswith("~") else (system_dir / image)
            items.append({
                "id": _game_id(rom), "title": title,
                "system": sid, "system_name": info["name"], "gen": info["gen"],
                "emu": info["emu"], "rom": str(rom), "bat": "",
                "image": str(rel_img.resolve()) if image and rel_img.exists() else "",
                "upgrades": info["upgrades"], "native_pc": False,
            })
            count += 1
            if count >= max_per_system:
                break
    return items


def system_summary(items: list[dict]) -> list[dict]:
    """Resumo por console: quantos jogos, emulador, melhorias disponíveis."""
    out: dict[str, dict] = {}
    for it in items:
        s = out.setdefault(it["system"], {
            "system": it["system"], "name": it["system_name"],
            "gen": it["gen"], "emu": it["emu"],
            "count": 0, "upgrades": it["upgrades"],
        })
        s["count"] += 1
    return sorted(out.values(), key=lambda x: (x["gen"], x["name"]))
