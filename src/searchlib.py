"""TurboPlay — busca inteligente (lupa): nome, marca/console e gênero.

Exemplos que funcionam:
  "super star soccer" → acha em NES/SNES (nome real: International Superstar Soccer)
  "futebol"           → lista TODOS os jogos de futebol, de qualquer console
  "ps1" / "playstation 1" → filtra só jogos de PS1
  "sonic"             → jogos com sonic em qualquer sistema
"""
from __future__ import annotations

import re
import unicodedata

# gênero → palavras que identificam (título ou série). PT-BR amigável.
_GENRE_KEYWORDS: dict[str, list[str]] = {
    "futebol": ["soccer", "fifa", "futebol", "world cup", "copa", "pes ",
                "pro evolution", "international superstar", "kick off",
                "sensible", "penalty", "brasil", "striker"],
    "corrida": ["racing", "speed", "rally", "grand prix", "mario kart",
                "top gear", "outrun", "crazy taxi", "need for speed", "nfs",
                "f-zero", "wipeout", "hydro thunder", "motor"],
    "luta": ["fighter", "fighting", "street fighter", "mortal kombat",
             "tekken", "king of fighters", "kof", "virtua fighter",
             "killer instinct", "samurai shodown", "fatal fury", "art of fighting"],
    "plataforma": ["platform", "mario", "sonic", "kirby", "donkey kong",
                   "crash bandicoot", "spyro", "rayman", "megaman", "mega man",
                   "castlevania", "jazz jackrabbit"],
    "tiro": ["shoot", "doom", "quake", "counter", "halo", "goldeneye",
             "time crisis", "house of the dead", "gradius", "rtype", "r-type",
             "1942", "1943", "darius"],
    "rpg": ["rpg", "final fantasy", "dragon quest", "zelda", "pokemon",
            "chrono", "secret of mana", "breath of fire", "suikoden",
            "persona", "tales of", "digimon"],
    "aventura": ["adventure", "zelda", "metroid", "tomb raider", "gta",
                 "grand theft", "link", "castlevania"],
    "esporte": ["sport", "nba", "nfl", "mlb", "nhl", "tennis", "golf",
                "bowling", "box", "skate", "tony hawk", "olympic",
                "track", "volley", "baseball", "basket"],
    "puzzle": ["puzzle", "tetris", "bust-a-move", "puyo", "bejeweled",
               "dr mario", "columns", "klax"],
}

# apelidos de console → id de sistema
_SYSTEM_ALIASES = {
    "nes": ["nes", "nintendo 8", "nintendinho"], "snes": ["snes", "super nintendo"],
    "ps1": ["ps1", "psx", "playstation 1", "play 1", "one"], "ps2": ["ps2", "playstation 2", "play 2"],
    "ps3": ["ps3", "playstation 3", "play 3"], "ps4": ["ps4", "playstation 4", "play 4"],
    "psp": ["psp", "portátil play"], "n64": ["n64", "nintendo 64", "nitendo 64"],
    "megadrive": ["mega drive", "megadrive", "genesis"], "dreamcast": ["dreamcast", "dc"],
    "gamecube": ["gamecube", "game cube", "gc"], "wii": ["wii"], "switch": ["switch"],
    "xbox": ["xbox", "xbox classic"], "xbox360": ["xbox 360", "xbox360"],
    "gba": ["gba", "game boy advance", "gameboy advance"],
    "gb": ["game boy", "gameboy", "gb"], "gbc": ["game boy color", "gbc"],
    "nds": ["nds", "nintendo ds", "ds"], "3ds": ["3ds", "nintendo 3ds"],
    "arcade": ["arcade", "fliperama"], "neogeo": ["neogeo", "neo geo"],
    "saturn": ["saturno", "saturn"], "mastersystem": ["master system", "mastersystem"],
    "sega32x": ["32x"], "segacd": ["sega cd", "mega cd"],
    "dos": ["dos", "pc dos"], "pc": ["pc", "windows"],
}

_WORD_SPLIT = re.compile(r"[\s\-_:]+")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def _tokens(s: str) -> set[str]:
    return {t for t in _WORD_SPLIT.split(_norm(s)) if t}


def search_library(items: list[dict], query: str) -> tuple[list[dict], str]:
    """Busca com fallback em cascata. Devolve (lista, descrição do filtro)."""
    q = _norm(query.strip())
    if not q:
        return items, ""
    q_tokens = _tokens(q)

    # 1. filtro por console/marca? ("ps1", "super nintendo"...)
    for sid, aliases in _SYSTEM_ALIASES.items():
        for a in aliases:
            if q == _norm(a) or q in {_norm(a)}:
                filtered = [i for i in items if i["system"] in
                            _alias_to_system_ids(sid)]
                if filtered:
                    return filtered, f"console: {sid}"

    # 2. busca por gênero ("futebol", "luta"...) — lista tudo do gênero
    for genre, words in _GENRE_KEYWORDS.items():
        if q == genre or q in _tokens(genre):
            hits = [i for i in items if _matches_any(i, words)]
            if hits:
                return hits, f"gênero: {genre}"

    # 3. busca por nome (fuzzy por tokens: todas as palavras batem)
    hits = [i for i in items if q_tokens <= _tokens(i["title"] + " " + i.get("system_name", ""))]
    if hits:
        return hits, "nome"
    # 3b. qualquer palavra bate
    hits = [i for i in items
            if any(t in _tokens(i["title"] + " " + i.get("system_name", ""))
                   for t in q_tokens)]
    if hits:
        return hits, "nome (parcial)"
    return [], "sem resultados"


def _alias_to_system_ids(alias: str) -> list[str]:
    """IDs de sistema no SAMBOX que correspondem ao apelido."""
    mapping = {
        "nes": ["nes", "famicom", "fds"], "snes": ["snes", "sfc", "snesbr", "snes-msu"],
        "ps1": ["psx"], "ps2": ["ps2", "ps2br"], "ps3": ["ps3", "ps32334"],
        "ps4": ["ps4"], "psp": ["psp"], "n64": ["n64", "n64br", "n64dd"],
        "megadrive": ["megadrive", "genesis", "megadrivebr", "megadrive-japan", "megadrive-msu"],
        "dreamcast": ["dreamcast"], "gamecube": ["gamecube"], "wii": ["wii"],
        "switch": ["switch", "switchbr"], "xbox": ["xbox"], "xbox360": ["xbox360"],
        "gba": ["gba", "gba2players", "gbabr", "gbah"], "gb": ["gb", "gb-msu", "gbh"],
        "gbc": ["gbc", "gbc2players", "gbch"], "nds": ["nds", "ndsbr"],
        "3ds": ["3ds"], "arcade": ["arcade", "mame", "hbmame", "model2", "model3",
                                    "naomi", "atomiswave", "psxmame"],
        "neogeo": ["neogeo", "neogeo64", "neogeocd"], "saturn": ["saturn"],
        "mastersystem": ["mastersystem", "mastersystembr"], "sega32x": ["sega32x"],
        "segacd": ["segacd"], "dos": ["dos"], "pc": ["pc", "windows", "ps5"],
    }
    return mapping.get(alias, [alias])


def _matches_any(item: dict, words: list[str]) -> bool:
    text = _norm(item["title"])
    return any(w in text for w in words)
