"""TurboPlay — watcher: detecta jogo novo em QUALQUER provedor.

O bug que motivou a reescrita: `_snapshot()` comparava só o mtime do diretório
raiz. Um download da Steam cria subpasta em `common\\` e dispara; uma ROM nova
cai dentro de `roms\\ps1\\` e NÃO mudava o mtime de `roms\\` — o evento se perdia.
Aqui a assinatura é a contagem de itens por raiz de primeiro nível (barato no
NTFS) mais o mtime das subpastas, o que cobre os dois casos.

Stdlib apenas: sem watchdog, sem polling pesado.
"""
from __future__ import annotations

import time
from pathlib import Path

from .classifier import classify
from .pipeline import _apply_layers, _load_state, _save_state
from .profiles import decide, detect_gpu
from .providers import scan_all, steam_libraries


def _watch_roots(sambox_root: Path | None = None) -> list[Path]:
    """Raízes onde jogo novo pode aparecer. Steam + SAMBOX + pastas custom."""
    roots: list[Path] = list(steam_libraries())
    root = sambox_root or Path(r"D:\Games\SAMBOX-Vfull\sistema\roms")
    if root.is_dir():
        roots.append(root)
    from .providers import custom_folders
    roots.extend(custom_folders())
    return [r for r in roots if r.is_dir()]


def _signature(roots: list[Path]) -> str:
    """Assinatura barata e que NÃO perde evento: (nome, mtime, contagem) por
    subpasta de primeiro nível. Custo: um iterdir por raiz."""
    parts: list[str] = []
    for root in roots:
        try:
            for sub in sorted(root.iterdir()):
                try:
                    st = sub.stat()
                    parts.append(f"{sub.name}:{st.st_mtime_ns}")
                except OSError:
                    continue
        except OSError:
            continue
    return "|".join(parts)


def _count_items(roots: list[Path]) -> int:
    """Contagem total de itens relevantes — usado como segunda rede de segurança
    quando um mtime não muda mas o conteúdo cresce."""
    n = 0
    for root in roots:
        try:
            for sub in root.iterdir():
                n += 1
                try:
                    if sub.is_dir():
                        n += sum(1 for _ in sub.iterdir())
                except OSError:
                    pass
        except OSError:
            continue
    return n


class LibraryWatcher:
    """Vigia as raízes; chama `on_change` quando a biblioteca muda.

    Usa as DUAS assinaturas (mtime por subpasta + contagem). Só dispara uma vez
    por mudança real e respeita um debounce para não inundar durante download.
    """

    def __init__(self, on_change, poll_sec: int = 20, debounce_sec: int = 60) -> None:
        self.on_change = on_change
        self.poll_sec = poll_sec
        self.debounce_sec = debounce_sec
        roots = _watch_roots()
        self._roots = roots
        self._last_sig = _signature(roots)
        self._last_count = _count_items(roots)
        self._last_fire = 0.0
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def loop(self) -> None:
        while not self._stop:
            time.sleep(self.poll_sec)
            try:
                sig = _signature(self._roots)
                cnt = _count_items(self._roots)
                if sig == self._last_sig and cnt == self._last_count:
                    continue
                self._last_sig, self._last_count = sig, cnt
                now = time.monotonic()
                if now - self._last_fire < self.debounce_sec:
                    continue      # debounce: baixa uma vez, não em rajada
                self._last_fire = now
                self.on_change()
            except Exception:
                continue    # resiliente: nunca derruba o watcher


def auto_optimize_new_games(dry_run: bool = False) -> dict:
    """Pipeline incremental: otimiza só o que ainda não está no estado.

    Regra de segurança: jogo bloqueado (MSIX), sem escrita, anti-cheat ou não-DX12
    é REGISTRADO como NOOP — para não ser reprocessado a cada passada — mas sem
    nenhuma escrita no disco.
    """
    gpu = detect_gpu()
    state = _load_state()
    applied: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []
    for g in scan_all():
        if g.id in state:
            continue
        cg = classify(g)
        p = decide(cg, gpu)
        if p.decision == "NOOP":
            state[g.id] = {"folder": g.folder, "title": g.title,
                           "decision": "NOOP", "installed_files": [],
                           "installed_dirs": []}
            skipped.append((g.title, p.reason))
            continue
        if dry_run:
            applied.append((g.title, p.decision))
            continue
        r = _apply_layers(cg, p, set())
        if r["ok"]:
            files = [p.dll_name, "OptiScaler.ini", "dlssg_sm86.ini"]
            if p.dll_name != "version.dll":
                files.append("version.dll")
            if "DLSSNR_FORK" in p.layers:
                files += ["nvngx_dlssnr.dll", "dxgi.dll"]
            state[g.id] = {"folder": g.folder, "title": g.title,
                           "decision": p.decision,
                           "installed_files": files,
                           "installed_dirs": (["OptiScaler", "Licenses_DLSSNR"]
                                              if "DLSSNR_FORK" in p.layers
                                              else ["D3D12_Optiscaler", "Licenses"])}
            # Mods da biblioteca `mods/<Jogo>/` vão junto, na entrada do jogo
            try:
                from .mods import auto_install_for_game
                m = auto_install_for_game(g.title, g.folder, Path(g.exe_path).name)
                for name in m:
                    applied.append((f"{g.title} · mod {name}", "mods"))
            except Exception:
                pass
            applied.append((g.title, p.decision))
    if not dry_run:
        _save_state(state)
    return {"applied": applied, "skipped": skipped}