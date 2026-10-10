"""TurboPlay — mods (Nexus e afins).

Funciona de dois jeitos:
  1. Manual: usuário escolhe um zip/RAR pra um jogo → extrai, detecta a
     estrutura e copia pra pasta certa do jogo. Registra cada arquivo num
     manifest (`turboinstall.mods.json` na pasta do jogo) pra poder remover.
  2. Automática: biblioteca `Projetos/TurboPlay/mods/<Jogo>/` — na hora de
     otimizar/jogar, qualquer mod ainda não instalado do jogo vai junto.

Regras de destino (heurística — a maioria dos mods de RE Framework/Opti):
  - zip/RAR com uma única pasta-raiz: merge do conteúdo dessa pasta.
  - arquivos `.dll` na raiz do mod: raiz do jogo (hooks/plugins)
  - pastas `reframework`, `autorun`, `NativeMods`, `FluffyModManager`: raiz do jogo
  - qualquer outra estrutura: copia tal como está para a raiz do jogo
    (compatível com Fluffy Mod Manager e Nexus "manual install").
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
MODS_DIR = PROJECT / "mods"
WINRAR = r"C:\Program Files\WinRAR\WinRAR.exe"

_NATIVE_DIRS = {"reframework", "autorun", "nativemods", "nativemods_pak",
                "fluffymodmanager", "chunkapaks", "pak"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


# ─── manifest ────────────────────────────────────────────────────────────────

def _manifest_path(game_folder: Path) -> Path:
    return game_folder / "turboinstall.mods.json"


def _load_manifest(game_folder: Path) -> list[dict]:
    p = _manifest_path(game_folder)
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save_manifest(game_folder: Path, mods: list[dict]) -> None:
    _manifest_path(game_folder).write_text(
        json.dumps(mods, indent=2, ensure_ascii=False), encoding="utf-8")


# ─── extração ────────────────────────────────────────────────────────────────

def extract_archive(archive: Path, dest: Path) -> tuple[bool, str]:
    """Extrai zip (stdlib) ou rar (WinRAR) para dest."""
    suffix = archive.suffix.lower()
    if suffix == ".zip":
        try:
            with zipfile.ZipFile(archive) as z:
                z.extractall(dest)
            return True, ""
        except (zipfile.BadZipFile, OSError) as e:
            return False, f"zip inválido: {e}"
    if suffix in (".rar", ".7z"):
        if not Path(WINRAR).is_file():
            return False, "WinRAR não encontrado para extrair o arquivo"
        r = subprocess.run([WINRAR, "x", "-o+", "-ibck",
                            str(archive), str(dest) + "/"],
                           capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            return False, f"WinRAR falhou (código {r.returncode})"
        return True, ""
    return False, f"formato não suportado: {archive.suffix}"


def _collapse_single_root(src: Path) -> Path:
    """Mods do Nexus costumam vir embrulhados numa pasta. Desembrulha.

    NÃO desembrulha pastas de destino reais (`reframework/` etc.):
    um zip com só `reframework/autorun/mod.lua` TEM que manter o caminho —
    desembrulhar jogava o lua em `autorun/` na raiz, onde o REFramework
    nunca lê (achado no teste de 09/10).
    """
    entries = [e for e in src.iterdir() if not e.name.startswith(".")]
    while (len(entries) == 1 and entries[0].is_dir()
           and entries[0].name.lower() not in _NATIVE_DIRS):
        src = entries[0]
        entries = [e for e in src.iterdir() if not e.name.startswith(".")]
    return src


def _install_rules(applied: dict[str, list[str]]) -> list[str]:
    """Arquivos já copiados, resolvendo colisões (`#1`, `#2`… suffixo)."""
    return applied


# ─── instalação ──────────────────────────────────────────────────────────────

@dataclass
class ModResult:
    ok: bool
    name: str
    files: list[str] = field(default_factory=list)
    error: str = ""


def install_mod(game_title: str, game_folder: str,
                archive: str, mod_name: str = "") -> ModResult:
    """Instala um mod (zip/rar) num jogo. Retorna o que foi copiado."""
    a = Path(archive)
    game = Path(game_folder)
    if not a.is_file():
        return ModResult(False, mod_name or a.name, [], "arquivo não existe")
    if not game.is_dir():
        return ModResult(False, mod_name or a.name, [], "pasta do jogo não existe")

    name = mod_name or a.stem
    with tempfile.TemporaryDirectory(prefix="turboplay_mod_") as tmp:
        src = Path(tmp) / "x"
        src.mkdir()
        ok, err = extract_archive(a, src)
        if not ok:
            return ModResult(False, name, [], err)
        src = _collapse_single_root(src)

        # nada a instalar?
        if not any(src.iterdir()):
            return ModResult(False, name, [], "arquivo vazio")

        copied: list[str] = []
        existing_owners: dict[str, str] = {}   # relpath → mod que já tinha
        manifest = _load_manifest(game)
        for m in manifest:
            for f in m.get("files", []):
                existing_owners[f.lower()] = m.get("name", "?")

        conflicts: list[str] = []
        for f in sorted(src.rglob("*")):
            rel = f.relative_to(src)
            dest = game / rel
            if not dest.resolve().is_relative_to(game.resolve()):
                continue  # path traversal — ignora
            if f.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            key = str(rel).lower()
            if key in existing_owners and existing_owners[key] != name:
                conflicts.append(f"{rel} (substitui mod '{existing_owners[key]}')")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            copied.append(str(rel))

        if not copied:
            return ModResult(False, name, [], "nenhum arquivo copiado")

        # actualiza manifest (remove entrada anterior do mesmo mod)
        manifest = [m for m in manifest if m.get("name") != name]
        manifest.append({
            "name": name,
            "archive": str(a),
            "installed": __import__("datetime").date.today().isoformat(),
            "files": copied,
            "replaced": conflicts,
        })
        _save_manifest(game, manifest)
        msg = f"{len(copied)} arquivo(s)"
        if conflicts:
            msg += f" · sobrescreveu: {', '.join(conflicts[:3])}"
        return ModResult(True, name, copied, msg)


def remove_mod(game_folder: str, mod_name: str) -> tuple[bool, str]:
    """Remove um mod pelo nome, apagando os arquivos registrados."""
    game = Path(game_folder)
    manifest = _load_manifest(game)
    entry = next((m for m in manifest if m.get("name") == mod_name), None)
    if not entry:
        return False, f"mod '{mod_name}' não está registrado"
    removed, missing = 0, 0
    for rel in entry.get("files", []):
        p = game / rel
        if p.is_file():
            try:
                p.unlink()
                removed += 1
            except OSError:
                missing += 1
        else:
            missing += 1
    rest = [m for m in manifest if m.get("name") != mod_name]
    _save_manifest(game, rest)
    return True, f"{removed} arquivo(s) apagado(s)"


def game_mods(game_folder: str) -> list[dict]:
    """Mods instalados num jogo (para listagem na GUI)."""
    return _load_manifest(Path(game_folder))


# ─── biblioteca automática: mods/<Jogo>/ ... ────────────────────────────────

def _match_mod_folder(game_title: str, exe_name: str) -> Path | None:
    """Acha `mods/<título>/` do jogo. Título ou nome do exe (ex.: 're3')."""
    if not MODS_DIR.is_dir():
        return None
    keys = {_norm(game_title), _norm(Path(exe_name).stem)}
    for d in sorted(MODS_DIR.iterdir()):
        if not d.is_dir():
            continue
        dn = _norm(d.name)
        if dn in keys or any(k and (k in dn or dn in k) for k in keys if len(k) > 3):
            return d
    return None


def auto_install_for_game(game_title: str, game_folder: str,
                          exe_name: str = "") -> list[str]:
    """Instala (1x) tudo que estiver em mods/<Jogo>/ e ainda não foi aplicado.

    Aceita zip/rar e também mods já soltos em subpastas (copiam direto).
    Devolve nomes instalados (para notificação).
    """
    src = _match_mod_folder(game_title, exe_name)
    if src is None:
        return []
    installed: list[str] = []
    already = {m.get("name") for m in _load_manifest(Path(game_folder))}
    for item in sorted(src.rglob("*")):
        if item.is_dir():
            continue
        if item.suffix.lower() in (".zip", ".rar", ".7z"):
            name = item.stem
            if name in already:
                continue
            r = install_mod(game_title, game_folder, str(item), name)
            if r.ok:
                installed.append(r.name)
    return installed
