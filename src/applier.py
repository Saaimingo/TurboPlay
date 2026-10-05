"""TurboPlay — aplicação das stacks com backup, rollback e verificação."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from .models import Game, Profile

STATE_DIR = Path.home() / "AppData" / "Local" / "TurboPlay"
BACKUP_DIR = STATE_DIR / "backups"
STATE_FILE = STATE_DIR / "installed.json"

# Versão do esquema do installed.json. Sobe quando a forma de instalar muda
# (slots de DLL, pastas, INIs). Sem isso, um build velho acha que o jogo já
# está otimizado pela stack antiga e pula — foi o que deixou o RDR2 sem fork
# em 04/10. Toda entrada grava o esquema; o pipeline compara antes de pular.
STATE_SCHEMA = 2

# URLs oficiais (D3 do DECISOES.md) — versões pinadas, hash verificada no download
OFFICIAL_SOURCES = {
    "OptiScaler": "https://github.com/optiscaler/OptiScaler/releases/download/v0.9.4/Optiscaler_0.9.4-final.20260718._MM.7z",
    "DLSS_Enabler": "https://www.nexusmods.com/site/mods/757?tab=files",  # requer login — cache local no MVP
    "SM86": {
        "version.dll": "https://raw.githubusercontent.com/sdli1995/dlssg_for_sm86/main/version.dll",
        "dlssg_sm86.ini": "https://raw.githubusercontent.com/sdli1995/dlssg_for_sm86/main/dlssg_sm86.ini",
    },
}

# Cache local já validado nesta máquina (usado enquanto não há hash registry)
CACHE_DIR = Path(r"D:\Games\MFG-NVIDIA-DLSS5\_downloads")

# ── stack DLSS5 + MFG (fork OptiScaler-DLSSNR v0.8.7 + Streamline oficial) ──
# Hashes fixados conforme docs/RELATORIO-2026-09-22.md §3. D3 manda nunca baixar
# "latest" às cegas: ou o hash bate, ou não instala.
FORK_DIR = CACHE_DIR / "optiscaler_dlssnr_0891" / "standard"
# A variante "-rtx40-mfg" traz o unlock Ada compilado dentro, mas o proprio
# docs/RTX40-MFG.md diz: "The option defaults off and only patches RTX 40/Ada".
# Na RTX 30 (Ampere) ele nao se aplica — o MFG aqui vem do proxy SM86 (version.dll)
# + Streamline. Por isso usamos a variante standard, que e a correta para nos.
FORK_VERSION = "0.8.91"
FORK_PINNED_ZIP_SHA256 = "19a2852bb3f88e09075e3ccc66e0318c52e83a5901d9020a10384ae49d59ff77"
STREAMLINE_DIR = CACHE_DIR / "streamline-sdk-2.14.1" / "extracted" / "bin" / "x64"
FORK_PINNED_SHA256 = "329694af"          # prefixo do SHA256SUMS oficial do fork
STREAMLINE_PINNED_SHA256 = "92c4d954"    # prefixo pinado no doc do fork

# A runtime NR (165 MB) NÃO vem no fork 087 — vem do pacote Tech Games 076,
# auditado em 21/09. O hash abaixo é o pinado no doc do fork para RTX 20/30/40
# (RELATORIO-2026-09-22 §2.3); a assinatura NVIDIA aparece inválida nessa build
# cross-gen por construção, então o hash é a garantia (D9/D12).
NR_EXPECTED_SHA256_PREFIX = "e67dee20"
NR_SEARCH_PATHS = [
    CACHE_DIR / "optiscaler_dlssnr_076",
]

_FORK_BACKEND_FILES = [
    "OptiScaler.dll", "OptiScaler.ini", "amd_fidelityfx_dx12.dll",
    "amd_fidelityfx_framegeneration_dx12.dll", "amd_fidelityfx_upscaler_dx12.dll",
    "amd_fidelityfx_vk.dll", "libxell.dll", "libxess.dll",
]
_STREAMLINE_DLLS = [
    "sl.interposer.dll", "sl.common.dll", "sl.dlss_g.dll",
    "sl.reflex.dll", "sl.pcl.dll", "nvngx_dlssg.dll",
]


def _sha256_prefix(path: Path, n: int = 8) -> str:
    return _sha256(path).lower()[:n]


def _parse_sha256sums(path: Path) -> dict[str, str]:
    """Lê um SHA256SUMS no formato GNU: `HASH *nome` (asterisco antes do nome)."""
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return out
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 64:
            out[parts[1].lstrip("*").lower()] = parts[0].lower()
    return out


def verify_fork_integrity() -> tuple[bool, str]:
    """Confere o cache do fork, do Streamline e da runtime NR contra os hashes
    pinados (D3). Nunca instala com hash divergente.

    Além dos arquivos soltos, confere o ZIP oficial: e ele que o D3 pinou
    (SHA256SUMS.txt do autor). O ZIP e a fonte da verdade do pacote.
    """
    zips = FORK_DIR.parent / "OptiScaler-NR-v0.8.91.zip"
    if zips.exists():
        got = _sha256(zips)
        if got.lower() != FORK_PINNED_ZIP_SHA256:
            return False, (f"hash do ZIP do fork diverge (esperado "
                            f"{FORK_PINNED_ZIP_SHA256[:8]}, veio {got[:8]}) — não instalar")
    if not FORK_DIR.is_dir():
        return False, f"cache do fork ausente: {FORK_DIR}"
    ini = FORK_DIR / "OptiScaler.ini"
    dll = FORK_DIR / "OptiScaler.dll"
    if not ini.exists() or not dll.exists():
        return False, "fork DLSSNR incompleto (OptiScaler.dll/.ini ausentes)"
    sums = FORK_DIR / "SHA256SUMS.txt"
    if sums.exists():
        recorded = _parse_sha256sums(sums)
        want = recorded.get(dll.name.lower())
        if want:
            got = _sha256(dll)
            if got != want:
                return False, f"hash do fork diverge (esperado {want[:8]}, veio {got[:8]})"
    if not STREAMLINE_DIR.is_dir() or not (STREAMLINE_DIR / "sl.dlss_g.dll").exists():
        return False, f"cache do Streamline ausente ou incompleto: {STREAMLINE_DIR}"
    nr = _find_nr_dll()
    if nr is None:
        return False, "nvngx_dlssnr.dll ausente — sem DLSS 5 (rode a busca no cache)"
    got = _sha256(nr)
    if not got.startswith(NR_EXPECTED_SHA256_PREFIX):
        return False, (f"hash da runtime NR diverge (esperado {NR_EXPECTED_SHA256_PREFIX}, "
                        f"veio {got[:8]}) — não instalar")
    return True, "fork + Streamline + NR com hash pinado OK"


def _find_nr_dll() -> Path | None:
    """Localiza a runtime NR validada (165 MB) no cache local."""
    for base in NR_SEARCH_PATHS:
        if base.is_dir():
            found = next(iter(base.rglob("nvngx_dlssnr.dll")), None)
            if found:
                return found
    if FORK_DIR.is_dir():
        found = next(iter(FORK_DIR.rglob("nvngx_dlssnr.dll")), None)
        if found:
            return found
    return None


def apply_dlssnr_fork(game: Game, profile: Profile) -> tuple[bool, str]:
    """Instala a stack DLSS 5 + MFG: fork OptiScaler-DLSSNR em dxgi.dll,
    Streamline oficial para FGOutput=dlssg, e a runtime NR.

    Slots (decisão D11/D12): o fork ocupa `dxgi.dll`; o proxy SM86 continua
    em `version.dll`, que é o nome que o jogo importa.
    """
    ok, why = verify_fork_integrity()
    if not ok:
        return False, f"DLSSNR_FORK ✗ ({why})"
    folder = Path(game.folder)
    _backup(game, ["dxgi.dll", "OptiScaler.ini", "version.dll", "dlssg_sm86.ini"])
    try:
        # 1. fork: backend OptiScaler
        shutil.copytree(FORK_DIR / "OptiScaler", folder / "OptiScaler", dirs_exist_ok=True)
        if (FORK_DIR / "OptiScaler").is_dir():
            for extra in FORK_DIR.glob("*.dll"):
                if extra.name not in ("OptiScaler.dll",):
                    shutil.copy2(extra, folder / extra.name)
        for f in _FORK_BACKEND_FILES:
            src = FORK_DIR / f
            if src.exists():
                shutil.copy2(src, folder / f)

        # 2. Streamline oficial (6 DLLs) para o FGOutput=dlssg
        sl_target = folder / "OptiScaler" / "streamline"
        sl_target.mkdir(parents=True, exist_ok=True)
        sl_src = None
        for cand in (STREAMLINE_DIR, STREAMLINE_DIR / "development",
                     CACHE_DIR / "streamline-sdk-2.14.1" / "extracted" / "bin" / "x64"):
            if (cand / "sl.dlss_g.dll").exists():
                sl_src = cand
                break
        if sl_src is None:
            return False, "DLSSNR_FORK ✗ (sl.dlss_g.dll não encontrado no cache Streamline)"
        for name in _STREAMLINE_DLLS:
            s = sl_src / name
            if s.exists():
                shutil.copy2(s, sl_target / name)

        # 3. runtime Neural Render (a DLL grande; hash conferido antes)
        nr = _find_nr_dll()
        if nr is None:
            return False, "DLSSNR_FORK ✗ (nvngx_dlssnr.dll ausente — sem DLSS 5)"
        shutil.copy2(nr, folder / "nvngx_dlssnr.dll")

        # 4. o fork entra no slot dxgi.dll
        fork_dll = FORK_DIR / "OptiScaler.dll"
        shutil.copy2(fork_dll, folder / (profile.dll_name or "dxgi.dll"))

        # 5. config do fork por seção
        _apply_ini_overrides(folder / "OptiScaler.ini", profile.ini_overrides)
        if profile.settings_xml_api:
            _force_settings_api(game, profile.settings_xml_api)
        for f in profile.files_to_remove:
            (folder / f).unlink(missing_ok=True)

        # 5b. o fork É o OptiScaler agora — o standalone classic (winmm.dll) e o
        # Nukems conflitam com ele e fazem o jogo recusar o hook (D12). Já estão
        # no backup feito no início desta função.
        removed: list[str] = []
        for stale in ("winmm.dll", "dlssg_to_fsr3_amd_is_better.dll",
                      "fakenvapi.dll"):
            p = folder / stale
            if p.exists():
                p.unlink()
                removed.append(stale)

        # 6. desinstalador próprio desta stack
        (folder / "Remove_TurboPlay.bat").write_text(
            "@echo off\r\nrem TurboPlay rollback (stack DLSS5+MFG)\r\n"
            "del /F /Q dxgi.dll OptiScaler.ini nvngx_dlssnr.dll version.dll "
            "dlssg_sm86.ini 2>nul\r\n"
            "rd /S /Q OptiScaler Licenses_DLSSNR 2>nul\r\n"
            "echo TurboPlay revertido.\r\npause\r\n",
            encoding="ascii")
        msg = "DLSS5_FORK ✓ (DLSS 5 NR + Streamline FG)"
        if removed:
            msg += f" · removido: {', '.join(removed)}"
        return True, msg
    except OSError as e:
        return False, f"DLSSNR_FORK ✗ (erro: {e})"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _backup(game: Game, files: list[str]) -> Path:
    bdir = BACKUP_DIR / game.id
    bdir.mkdir(parents=True, exist_ok=True)
    for name in files:
        src = Path(game.folder) / name
        if src.exists():
            shutil.copy2(src, bdir / name)
    (bdir / "game.json").write_text(json.dumps(game.to_dict(), indent=2), encoding="utf-8")
    return bdir


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state["_schema"] = STATE_SCHEMA
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def state_entry_for(game: Game, profile: Profile) -> dict:
    """Entrada de estado coerente com o perfil que foi realmente instalado."""
    fork = "DLSSNR_FORK" in profile.layers
    files = [profile.dll_name, "OptiScaler.ini", "dlssg_sm86.ini"]
    if profile.dll_name != "version.dll":
        files.append("version.dll")
    if fork:
        files += ["nvngx_dlssnr.dll"]
    return {
        "folder": game.folder,
        "title": game.title,
        "decision": profile.decision,
        "layers": list(profile.layers),
        "dll_name": profile.dll_name,
        "fork_version": FORK_VERSION,
        "schema": STATE_SCHEMA,
        "installed_files": files,
        "installed_dirs": (["OptiScaler", "Licenses_DLSSNR"] if fork
                           else ["D3D12_Optiscaler", "Licenses"]),
    }


def is_state_current(entry: dict, profile: Profile) -> tuple[bool, str]:
    """O que está no disco bate com o que o perfil de hoje instalaria?

    Três testes, nessa ordem: esquema (geração do estado), camadas aplicadas e
    slot de DLL. Qualquer divergência = reinstalar, nunca assumir.
    """
    if not isinstance(entry, dict):
        return False, "entrada de estado invalida"
    if entry.get("schema") != STATE_SCHEMA:
        return False, (f"estado de esquema {entry.get('schema', 'antigo')} "
                       f"≠ {STATE_SCHEMA} — instalado por uma versao anterior")
    if "DLSSNR_FORK" in profile.layers:
        got = entry.get("fork_version")
        if got != FORK_VERSION:
            return False, (f"fork instalado e {got or 'antigo'} "
                           f"≠ {FORK_VERSION} — reinstalando o componente")
    if entry.get("layers") != list(profile.layers):
        return False, (f"camadas no disco {entry.get('layers')} "
                       f"≠ perfil de hoje {list(profile.layers)}")
    if entry.get("dll_name") != profile.dll_name:
        return False, (f"slot {entry.get('dll_name')} ≠ {profile.dll_name}")
    return True, "estado confere com o perfil"


def _apply_ini_overrides(ini: Path, overrides: dict) -> None:
    """Aplica overrides no OptiScaler.ini. Chave "Seção/Chave" escopa pela seção;
    "Chave" sozinha substitui a 1ª ocorrência. Idempotente."""
    import re
    if not ini.exists() or not overrides:
        return
    text = ini.read_text(encoding="utf-8", errors="ignore")
    for key, value in overrides.items():
        if "/" in key:
            section, name = key.split("/", 1)
            sec_re = re.compile(
                rf"(\[{re.escape(section)}\].*?)(?=\n\[|\Z)", re.DOTALL | re.IGNORECASE)
            m = sec_re.search(text)
            if not m:
                text += f"\n[{section}]\n{name} = {value}\n"
                continue
            body = m.group(1)
            line_re = re.compile(
                rf"^{re.escape(name)}\s*=.*$", re.MULTILINE | re.IGNORECASE)
            if line_re.search(body):
                body = line_re.sub(f"{name} = {value}", body)
            else:
                body += f"\n{name} = {value}"
            text = text[:m.start(1)] + body + text[m.end(1):]
        else:
            line_re = re.compile(rf"^{re.escape(key)}\s*=.*$",
                                 re.MULTILINE | re.IGNORECASE)
            if line_re.search(text):
                text = line_re.sub(f"{key} = {value}", text, count=1)
    ini.write_text(text, encoding="utf-8")


def _force_settings_api(game: Game, api_token: str) -> bool:
    """Força a API gráfica no settings.xml do jogo (ex.: Vulkan→DX12).
    FG injetável só funciona em DX12; alguns jogos defaultam pra Vulkan."""
    import re
    sdir = Path.home() / "OneDrive" / "Documents"
    candidates = [sdir, Path.home() / "Documents"]
    for base in candidates:
        for xml in (base / "Rockstar Games" / game.title / "Settings" / "system.xml",
                    base / "Rockstar Games" / "Red Dead Redemption 2" / "Settings" / "system.xml"):
            if xml.exists():
                text = xml.read_text(encoding="utf-8", errors="ignore")
                new = re.sub(r"<API>[^<]*</API>", f"<API>{api_token}</API>", text, count=1)
                if new != text:
                    bak = xml.with_suffix(".xml.tp-bak")
                    if not bak.exists():
                        xml.replace(bak)
                        xml.write_text(new, encoding="utf-8")
                    else:
                        xml.write_text(new, encoding="utf-8")
                    return True
                return False
    return False


def apply_optiscaler(game: Game, profile: Profile) -> bool:
    """Instala OptiScaler a partir do cache local validado (7z já extraído)."""
    src = CACHE_DIR / "optiscaler_094"
    if not src.is_dir():
        print(f"  ✗ cache OptiScaler ausente: {src}")
        return False
    folder = Path(game.folder)
    files = ["OptiScaler.ini", "amd_fidelityfx_dx12.dll",
             "amd_fidelityfx_framegeneration_dx12.dll", "amd_fidelityfx_upscaler_dx12.dll",
             "amd_fidelityfx_vk.dll", "libxell.dll", "libxess.dll",
             "libxess_dx11.dll", "libxess_fg.dll", "dlssg_to_fsr3_amd_is_better.dll"]
    _backup(game, ["winmm.dll", "dxgi.dll", "version.dll", "OptiScaler.ini"])
    try:
        shutil.copytree(src / "D3D12_Optiscaler", folder / "D3D12_Optiscaler", dirs_exist_ok=True)
        shutil.copytree(src / "Licenses", folder / "Licenses", dirs_exist_ok=True)
        for f in files:
            if (src / f).exists():
                shutil.copy2(src / f, folder / f)
        dll_name = profile.dll_name or "dxgi.dll"
        shutil.copy2(src / "OptiScaler.dll", folder / dll_name)
        # overrides de INI do perfil (por seção) + API forçada no settings do jogo
        ini = folder / "OptiScaler.ini"
        _apply_ini_overrides(ini, profile.ini_overrides)
        if profile.settings_xml_api:
            _force_settings_api(game, profile.settings_xml_api)
        for f in profile.files_to_remove:
            (folder / f).unlink(missing_ok=True)
        # desinstalador
        uni = folder / "Remove_TurboPlay.bat"
        uni.write_text(
            "@echo off\r\nrem TurboPlay rollback\r\ndel /F /Q \"" + dll_name +
            "\" OptiScaler.ini fakenvapi.dll dlssg_to_fsr3_amd_is_better.dll 2>nul\r\n"
            "rd /S /Q D3D12_Optiscaler Licenses 2>nul\r\n"
            "echo Turboplay revertido.\r\npause\r\n",
            encoding="ascii",
        )
        return True
    except OSError as e:
        print(f"  ✗ erro na instalação: {e}")
        return False


def reconfigure_optiscaler(game: Game, profile: Profile) -> bool:
    """Re-aplica overrides de INI + API forçada num jogo já instalado (leve, idempotente).
    Usado quando o perfil ganha aprendizado novo (ex.: correção de FG)."""
    folder = Path(game.folder)
    if not (folder / "OptiScaler.ini").exists():
        return False
    _apply_ini_overrides(folder / "OptiScaler.ini", profile.ini_overrides)
    if profile.settings_xml_api:
        _force_settings_api(game, profile.settings_xml_api)
    return True


def apply_sm86(game: Game, profile: Profile) -> bool:
    """Instala proxy dlssg_for_sm86 (version.dll + ini)."""
    src = CACHE_DIR / "dlssg_sm86_035"
    if not (src / "version.dll").exists():
        print(f"  ✗ cache SM86 ausente: {src}")
        return False
    folder = Path(game.folder)
    _backup(game, ["version.dll", "dlssg_sm86.ini"])
    try:
        shutil.copy2(src / "version.dll", folder / "version.dll")
        shutil.copy2(src / "dlssg_sm86.ini", folder / "dlssg_sm86.ini")
        return True
    except OSError as e:
        print(f"  ✗ erro na instalação SM86: {e}")
        return False


def rollback(game_id: str) -> bool:
    state = _load_state()
    entry = state.get(game_id)
    if not entry:
        return False
    folder = Path(entry["folder"])
    bdir = BACKUP_DIR / game_id
    # remove arquivos instalados
    for name in entry.get("installed_files", []):
        (folder / name).unlink(missing_ok=True)
    for d in entry.get("installed_dirs", []):
        shutil.rmtree(folder / d, ignore_errors=True)
    # restaura backups
    if bdir.is_dir():
        for f in bdir.iterdir():
            if f.is_file() and f.name != "game.json":
                shutil.copy2(f, folder / f.name)
    state.pop(game_id, None)
    _save_state(state)
    return True


def fg_gate_failed(folder: str) -> bool:
    """O jogo recusou o frame generation nesta sessao?

    O proxy SM86 escreve `dlssg_sm86/logs/backend_<pid>.jsonl` com o evento
    `fg_gate_create_feature`. Status `0xbad0000b` significa que o NGX recusou
    a arquitetura — tipicamente porque o jogo nao cumpre o contrato de
    apresentacao do Streamline (nao chama GetCurrentBackBufferIndex, nao tem
    Reflex). Nao e problema de configuracao e nao adianta mexer em INI.
    """
    logs = Path(folder) / "dlssg_sm86" / "logs"
    if not logs.is_dir():
        return False
    candidates = sorted(logs.glob("backend_*.jsonl"), key=lambda p: p.stat().st_mtime,
                        reverse=True)
    for lg in candidates[:3]:
        try:
            text = lg.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if '"fg_gate_create_feature"' not in text:
            continue
        if '"0xbad0000b"' in text or '"succeeded":false' in text:
            return True
        if '"succeeded":true' in text:
            return False
    return False


def maybe_fallback_to_fsrfg(game: Game, profile: Profile) -> tuple[bool, str]:
    """Se o jogo recusou o FG via Streamline, tenta a rota FSR.

    FSR 3.1B gera frames sem depender do contrato do Streamline — e e o que
    realmente rodava no RDR2 antes de mexermos. Nao e DLSS-G, mas e FG de
    verdade, e o jogador recebe frames em vez de nao receber nada.

    Idempotente: se ja caimos para fsrfg, nao faz nada.
    """
    if "DLSSNR_FORK" not in profile.layers:
        return False, ""
    folder = Path(game.folder)
    ini = folder / "OptiScaler.ini"
    if not ini.exists():
        return False, ""
    if not fg_gate_failed(str(folder)):
        return False, ""
    try:
        current = _read_ini_value(ini, "FrameGen", "FGOutput")
    except OSError:
        return False, ""
    if (current or "").lower() == "fsrfg":
        return False, ""
    _apply_ini_overrides(ini, {"FrameGen/FGOutput": "fsrfg"})
    return True, ("o jogo recusou o FG do Streamline (0xbad0000b) — "
                  "trocado para FSR 3.1B, que funciona sem esse requisito")


def _read_ini_value(ini: Path, section: str, name: str) -> str | None:
    """Le uma chave do INI respeitando a secao. None se nao achar."""
    import re
    try:
        text = ini.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    m = re.search(rf"\[{re.escape(section)}\](.*?)(?=\n\[|\Z)", text,
                  re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    k = re.search(rf"^{re.escape(name)}\s*=\s*(.+)$", m.group(1),
                  re.MULTILINE | re.IGNORECASE)
    return k.group(1).strip() if k else None


def verify(game: Game) -> str:
    """Lê logs das camadas após o primeiro launch. Retorna status legível."""
    folder = Path(game.folder)
    logs = folder / "dlssg_sm86" / "logs"
    if logs.is_dir():
        for lg in logs.glob("backend_*.jsonl"):
            try:
                if '"install"' in lg.read_text(encoding="utf-8", errors="ignore") \
                        and "active=true" in lg.read_text(encoding="utf-8", errors="ignore"):
                    return "MFG_NVIDIA_OK"
            except OSError:
                pass
    if (folder / "OptiScaler.log").exists():
        return "OPTISCALER_OK"
    return "PENDENTE_PRIMEIRO_LAUNCH"


def run_pipeline(games: list[Game], profiles: dict[str, Profile], dry_run: bool = True) -> list[dict]:
    state = _load_state()
    results = []
    for g in games:
        p = profiles.get(g.id)
        if not p or p.decision == "NOOP":
            results.append({"game": g.title, "decision": p.decision if p else "?", "applied": False})
            continue
        applied = False
        if not dry_run:
            for layer in p.layers:
                if layer == "OptiScaler":
                    applied = apply_optiscaler(g, p)
                elif layer == "SM86":
                    applied = apply_sm86(g, p) or applied
                elif layer == "DLSS_Enabler":
                    print("  ⚠ DLSS Enabler: requer download manual (Nexus) — cache no MVP")
            if applied:
                state[g.id] = {"folder": g.folder, "title": g.title,
                               "decision": p.decision,
                               "installed_files": [p.dll_name, "OptiScaler.ini",
                                                   "version.dll", "dlssg_sm86.ini"],
                               "installed_dirs": ["D3D12_Optiscaler", "Licenses"]}
                _save_state(state)
        results.append({"game": g.title, "decision": p.decision,
                        "applied": applied, "layers": p.layers})
    return results
