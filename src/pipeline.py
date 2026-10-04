"""TurboPlay — pipeline completo: scan → classify → decide → apply → verify."""
from __future__ import annotations

import json
from pathlib import Path

from .applier import (apply_optiscaler, apply_sm86, reconfigure_optiscaler,
                      apply_dlssnr_fork, verify, _load_state, _save_state,
                      state_entry_for, is_state_current)
from .classifier import classify
from .enabler import try_install_enabler
from .profiles import decide, detect_gpu
from .providers import scan_all


def _looks_like_sm86(dll: Path) -> bool:
    """O version.dll da pasta é o proxy dlssg_for_sm86 ou outra coisa?

    O proxy carrega a string 'dlssg_sm86' no binário. Sem essa checagem,
    reescreveríamos o version.dll original do jogo — o que pode quebrá-lo.
    """
    try:
        with dll.open("rb") as fh:
            blob = fh.read(4 << 20)
    except OSError:
        return False
    low = blob.lower()
    return b"dlssg_sm86" in low or b"dlssg_for_sm86" in low


def _apply_layers(game, profile, layers_done: set[str]) -> dict:
    """Instala as camadas do perfil. Idempotente."""
    notes = []
    ok_any = False
    for layer in profile.layers:
        if layer in layers_done:
            continue
        if layer == "OptiScaler":
            ok = apply_optiscaler(game, profile)
            notes.append(("OptiScaler ✓" if ok else "OptiScaler ✗ (cache ausente)"))
            ok_any = ok or ok_any
        elif layer == "SM86":
            # SM86 entra SEMPRE em version.dll (D11). O fork entra em dxgi.dll
            # (D12) — slots diferentes, convivem. Só é pulado se o jogo já tem
            # um version.dll que não é o proxy (ex.: NvidiaNGX original).
            existing = Path(game.folder) / "version.dll"
            if existing.exists() and not _looks_like_sm86(existing):
                notes.append("SM86 ignorado: version.dll já existe e não é o proxy SM86")
                layers_done.add(layer)
                continue
            ok = apply_sm86(game, profile)
            notes.append(("SM86 ✓" if ok else "SM86 ✗ (cache ausente)"))
            ok_any = ok or ok_any
        elif layer == "DLSS_Enabler":
            ok, msg = try_install_enabler(game)
            notes.append(msg)
            ok_any = ok or ok_any
        elif layer == "DLSSNR_FORK":
            ok, msg = apply_dlssnr_fork(game, profile)
            notes.append(msg)
            ok_any = ok or ok_any
        layers_done.add(layer)
    return {"ok": ok_any, "notes": notes}


def optimize_one(game_id: str) -> dict:
    """Garante otimização de UM jogo (pré-launch JIT)."""
    gpu = detect_gpu()
    games = [classify(g) for g in scan_all()]
    for g in games:
        if g.id == game_id:
            p = decide(g, gpu)
            state = _load_state()
            prev = state.get(g.id)
            if prev:
                current, why = is_state_current(prev, p)
                if current:
                    # Com Enabler ativo, o optiscaler.ini pertence ao OptiScaler
                    # embutido dele — não reconfigurar por cima (evita conflito).
                    if prev.get("enabler"):
                        return {"applied": True, "cached": True, "decision": p.decision,
                                "reconfigured": False, "enabler": True}
                    ok = reconfigure_optiscaler(g, p)
                    return {"applied": True, "cached": True, "decision": p.decision,
                            "reconfigured": ok}
                # estado de geração antiga: reaplica a stack de hoje
                notes = _install(g, p, state, dry_run=False)
                _save_state(state)
                return {"applied": not any("✗" in n for n in notes),
                        "cached": False, "decision": p.decision,
                        "reapplied": why, "notes": notes}
            if p.decision == "NOOP":
                return {"applied": False, "noop": True, "reason": p.reason}
            notes = _install(g, p, state, dry_run=False)
            _save_state(state)
            return {"applied": not any("✗" in n for n in notes),
                    "decision": p.decision, "notes": notes}
            return {"applied": r["ok"], "decision": p.decision, "notes": r["notes"]}
    return {"applied": False, "error": "jogo não encontrado"}


def get_library() -> list[dict]:
    """Biblioteca de jogos para a GUI (com status de otimização)."""
    state = _load_state()
    out = []
    for g in scan_all():
        entry = state.get(g.id, {})
        out.append({
            "id": g.id, "title": g.title, "source": g.source,
            "launch_path": g.launch_path or g.exe_path,
            "optimized": g.id in state and entry.get("decision") != "NOOP",
            "blocked": g.protected_install or not g.writable,
            "reason": g.blocked_reason,
        })
    return out


def _install(g, p, state: dict, dry_run: bool) -> list[str]:
    """Aplica as camadas do perfil e grava o estado coerente. Por jogo."""
    if dry_run:
        return [f"dry-run: instalaria {' + '.join(p.layers)}"]
    # `layers_done` é SEMPRE novo: antes era compartilhado no laço e fazia o
    # 2º jogo em diante pular todas as camadas (achado em 04/10).
    r = _apply_layers(g, p, set())
    if r["ok"]:
        state[g.id] = state_entry_for(g, p)
    return r["notes"]


def run_full(auto_apply: bool = True, dry_run: bool = False) -> dict:
    """Executa o ciclo completo e devolve resumo para GUI/CLI.

    `dry_run=True` nunca escreve em jogo nem em `installed.json`: serve para
    responder "o que o TurboPlay faria?" antes deauthorize qualquer coisa.
    """
    gpu = detect_gpu()
    games = [classify(g) for g in scan_all()]
    state = _load_state()
    results = []
    for g in games:
        p = decide(g, gpu)
        entry = {
            "title": g.title, "source": g.source, "exe": g.exe_path,
            "api": g.api, "upscaler": g.upscaler, "fg_native": g.fg_native,
            "anticheat": g.anticheat,
            "decision": p.decision, "reason": p.reason, "layers": p.layers,
            "applied": False, "notes": [],
        }
        prev = state.get(g.id)
        if prev and p.decision == "NOOP":
            entry["notes"].append(f"registrado, sem ação: {p.reason}")
            entry["applied"] = False
        elif prev:
            # O que está no disco bate com o perfil de hoje?
            current, why = is_state_current(prev, p)
            if current:
                if not dry_run:
                    reconfigure_optiscaler(g, p)
                entry["notes"].append("já otimizado ✓ (config revalidada)")
                entry["applied"] = True
            else:
                entry["notes"].append(f"reaplicando: {why}")
                notes = _install(g, p, state, dry_run)
                entry["notes"].extend(notes)
                entry["applied"] = bool(notes) and not any("✗" in n for n in notes)
        elif auto_apply and p.decision != "NOOP":
            if dry_run:
                entry["applied"] = True
                entry["notes"] = [f"dry-run: instalaria {' + '.join(p.layers)}"]
                results.append(entry)
                continue
            notes = _install(g, p, state, dry_run)
            entry["notes"].extend(notes)
            entry["applied"] = bool(notes) and not any("✗" in n for n in notes)
        results.append(entry)
    if not dry_run:
        _save_state(state)
    return {"gpu": gpu, "games": results, "dry_run": dry_run,
            "summary": {
                "total": len(results),
                "otimizados": sum(1 for r in results if r["applied"]),
                "intocaveis": sum(1 for r in results if r["decision"] == "NOOP"),
            }}


def rollback_all() -> int:
    from .applier import rollback
    state = _load_state()
    n = 0
    for gid in list(state.keys()):
        if rollback(gid):
            n += 1
    return n
