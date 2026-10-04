"""TurboPlay — catálogo de sistemas (consoles) emulados.

Cada sistema mapeia: nome amigável, badge, geração, emulador padrão do
SAMBOX/RetroBat e as melhorias recomendadas (perfil de emulador).
"""
from __future__ import annotations

ROM_EXTS = {".cue", ".chd", ".iso", ".img", ".bin", ".pbp", ".mdf", ".gcm",
            ".rvz", ".wbfs", ".wia", ".nsp", ".xci", ".nds", ".cia", ".3ds",
            ".cci", ".gba", ".gb", ".gbc", ".nes", ".fds", ".sfc", ".smc",
            ".sms", ".gg", ".gen", ".md", ".32x", ".sat", ".sc", ".sgd",
            ".n64", ".z64", ".v64", ".ndd", ".d64", ".t64", ".prg", ".dsk",
            ".m3u", ".lnk", ".elf", ".vag", ".a26", ".a52", ".col", ".int",
            ".rom", ".vec", ".ws", ".wsc", ".ngp", ".ngc", ".pce", ".sgx",
            ".smc", ".fig", ".sfc", ".vb", ".uze", ".7z", ".zip"}

# sistema → (nome amigável, geração, emulador SAMBOX, melhorias)
SYSTEMS: dict[str, dict] = {
    # Nintendo
    "nes":       {"name": "Nintendo NES",        "gen": 3,  "emu": "retroarch",
                  "upgrades": ["Resolução interna 4-8x (xBR/ScaleFX)", "Paleta padrão NTSC", "Run-ahead p/ input lag"]},
    "snes":      {"name": "Super Nintendo",      "gen": 4,  "emu": "retroarch",
                  "upgrades": ["Resolução interna 4x", "MSU-1 (trilha CD)", "Beam racing/superfx overclock"]},
    "snes-msu":  {"name": "Super Nintendo MSU",  "gen": 4,  "emu": "retroarch", "upgrades": []},
    "n64":       {"name": "Nintendo 64",         "gen": 5,  "emu": "mupen64",
                  "upgrades": ["GLideN64 4K + texture pack", "PGXP-like (parallel-RDP)", "60fps patches"]},
    "n64dd":     {"name": "Nintendo 64DD",       "gen": 5,  "emu": "mupen64", "upgrades": []},
    "gb":        {"name": "Game Boy",            "gen": 4,  "emu": "retroarch", "upgrades": ["Paleta colorida", "Resolução 4x"]},
    "gbc":       {"name": "Game Boy Color",      "gen": 4,  "emu": "retroarch", "upgrades": ["Resolução 4x"]},
    "gba":       {"name": "Game Boy Advance",    "gen": 6,  "emu": "mgba",
                  "upgrades": ["Resolução 4x", "Shaders LCD-ghosting"]},
    "nds":       {"name": "Nintendo DS",         "gen": 7,  "emu": "melonds", "upgrades": ["Resolução 4x", "Layout tela grande"]},
    "3ds":       {"name": "Nintendo 3DS",        "gen": 8,  "emu": "citra", "upgrades": ["Resolução interna 4x", "Texturas HD"]},
    "switch":    {"name": "Nintendo Switch",     "gen": 9,  "emu": "ryujinx",
                  "upgrades": ["Mods de resolução/60fps", "Texturas HD", "Fork ryubing-dlss5 (DLSS5+FG!)"]},
    "gamecube":  {"name": "GameCube",            "gen": 6,  "emu": "dolphin-emu",
                  "upgrades": ["Resolução interna 4K", "Texturas HD", "Mods 60fps"]},
    "wii":       {"name": "Wii",                 "gen": 7,  "emu": "dolphin-emu",
                  "upgrades": ["Resolução 4K", "Wiimote por mouse", "Texturas HD"]},
    "wiiu":      {"name": "Wii U",               "gen": 8,  "emu": "cemu",
                  "upgrades": ["Resolução 4K", "Graphic packs (60fps)", "Texturas HD"]},

    # PlayStation
    "psx":       {"name": "PlayStation 1",       "gen": 5,  "emu": "duckstation",
                  "upgrades": ["Resolução interna 4K+", "PGXP (geometria 3D)", "Texture filtering", "Culling corrigido"]},
    "ps2":       {"name": "PlayStation 2",       "gen": 6,  "emu": "pcsx2",
                  "upgrades": ["Resolução interna 4K", "Texture filtering", "Widescreen patches", "No-interlacing"]},
    "ps3":       {"name": "PlayStation 3",       "gen": 7,  "emu": "rpcs3",
                  "upgrades": ["Resolução nativa 4K (RSX)", "Texturas HD", "Mods FPS"]},
    "psp":       {"name": "PlayStation Portable", "gen": 7, "emu": "ppsspp",
                  "upgrades": ["Resolução 4-8x", "Texturas HD", "2x texture scaling"]},
    "psvita":    {"name": "PS Vita",             "gen": 8,  "emu": "vita3k", "upgrades": ["Resolução 2-4x"]},
    "ps4":       {"name": "PlayStation 4",       "gen": 8,  "emu": "shadps4",
                  "upgrades": ["Resolução interna (RPU)", "Mods de FPS (progressivos)"]},
    "ps5":       {"name": "PlayStation 5",       "gen": 9,  "emu": "shadps4",
                  "upgrades": ["Jogos PC nativos disfarçados → stack MFG/DLSS", "Mods FPS"]},

    # Sega
    "mastersystem": {"name": "Master System",    "gen": 3,  "emu": "retroarch", "upgrades": ["Resolução 4x"]},
    "megadrive":    {"name": "Mega Drive",       "gen": 4,  "emu": "retroarch",
                  "upgrades": ["Resolução 4x", "Overclock do 68000 (opcional)"]},
    "megadrive-msu": {"name": "Mega Drive MSU",  "gen": 4,  "emu": "retroarch", "upgrades": []},
    "segacd":   {"name": "Sega CD",             "gen": 4,  "emu": "retroarch", "upgrades": ["Resolução 4x"]},
    "sega32x":  {"name": "Sega 32X",            "gen": 4,  "emu": "retroarch", "upgrades": []},
    "saturn":   {"name": "Sega Saturn",         "gen": 5,  "emu": "mednafen",
                  "upgrades": ["Resolução 4x", "Shaders Cristal/Curvature"]},
    "dreamcast": {"name": "Dreamcast",          "gen": 6,  "emu": "flycast",
                  "upgrades": ["Resolução 4K", "Texturas HD", "Widescreen cheats"]},
    "gamegear": {"name": "Game Gear",           "gen": 4,  "emu": "retroarch", "upgrades": []},

    # Xbox
    "xbox":     {"name": "Xbox (clássico)",     "gen": 6,  "emu": "xemu",
                  "upgrades": ["Resolução interna 4K", "Widescreen hacks"]},
    "xbox360":  {"name": "Xbox 360",            "gen": 7,  "emu": "xenia",
                  "upgrades": ["Resolução interna (canary)", "Mods de resolução"]},
    "xboxone":  {"name": "Xbox One",            "gen": 8,  "emu": "xenia", "upgrades": []},

    # Arcade e outros
    "arcade":   {"name": "Arcade",              "gen": 0,  "emu": "mame", "upgrades": ["Shaders CRT", "Resolução 4x"]},
    "cps1":     {"name": "Arcade CPS1",         "gen": 0,  "emu": "fbneo", "upgrades": ["Shaders CRT"]},
    "cps2":     {"name": "Arcade CPS2",         "gen": 0,  "emu": "fbneo", "upgrades": ["Shaders CRT"]},
    "cps3":     {"name": "Arcade CPS3",         "gen": 0,  "emu": "fbneo", "upgrades": ["Shaders CRT"]},
    "neogeo":   {"name": "Neo Geo",             "gen": 4,  "emu": "fbneo", "upgrades": ["Shaders CRT", "Resolução 4x"]},
    "atari2600": {"name": "Atari 2600",         "gen": 2,  "emu": "stella", "upgrades": []},
    "pcengine": {"name": "PC Engine",           "gen": 4,  "emu": "retroarch", "upgrades": ["Resolução 4x"]},
    "dos":      {"name": "PC (DOS)",            "gen": 0,  "emu": "dosbox",
                  "upgrades": ["Resolução/renders 4K", "Shaders CRT-Royale"]},
    "pc":       {"name": "PC (Windows)",        "gen": 0,  "emu": "",  "upgrades": ["Rota nativa MFG/DLSS"]},
}


_ALIASES = {
    "3do": "3do", "3d0": "3do",
    "fds": "nes", "famicom": "nes", "sfc": "snes", "snesbr": "snes",
    "n64br": "n64", "mastersystembr": "mastersystem",
    "megadrive-japan": "megadrive", "megadrivebr": "megadrive",
    "gb-msu": "gb", "gbh": "gb", "gbc2players": "gbc", "gbch": "gbc",
    "gba2players": "gba", "gbabr": "gba", "gbah": "gba",
    "ndsbr": "nds", "switchbr": "switch", "ps2br": "ps2",
    "ps32334": "ps3", "ps5": "ps5", "ps4eps5installars": "ps5",
    "snes-msu": "snes-msu", "msu": "snes-msu",
    "snesmsu": "snes-msu", "megadrive-msu": "megadrive-msu",
    "atarist": "atarist", "atarilynx": "atarilynx",
    "pcenginecd": "pcengine", "sgb": "gbc", "sms": "mastersystem",
    "genesis": "megadrive", "segagenesis": "megadrive",
    "supergrafx": "pcengine", "virtualboy": "virtualboy",
    "neogeocd": "neogeocd", "neogeo64": "neogeo",
    "model2": "arcade", "model3": "arcade", "naomi": "arcade",
    "atomiswave": "arcade", "hbmame": "arcade", "psxmame": "arcade",
    "mame": "arcade", "fbneo": "arcade", "neogeo": "neogeo",
}


def system_info(system_id: str) -> dict:
    sid = system_id.lower()
    sid = _ALIASES.get(sid, sid)
    info = SYSTEMS.get(sid)
    if info:
        return {"id": sid, **info}
    # fallback: tenta sem sufixos comuns de variantes locais
    base = sid.split("-")[0]
    if base in SYSTEMS:
        return {"id": base, **SYSTEMS[base]}
    return {"id": sid, "name": system_id.upper(), "gen": 0, "emu": "retroarch",
            "upgrades": []}
