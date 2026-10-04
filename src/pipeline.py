"""TurboPlay — pipeline completo: scan → classify → decide → apply → verify."""
from __future__ import annotations

import json

from .applier import (apply_optiscaler, apply_sm86, reconfigure_optiscaler,
                      apply_dlssnr_fork, verify, _load_state, _save_state)
from .classifier import classify
from .enabler import try_install_enabler
from .profiles import decide, detect_gpu
from .providers import scan_all


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
            if profile.dll_name and profile.dll_name != "version.dll":
                notes.append(f"SM86 ignorado: slot '{profile.dll_name}.dll' ocupado pelo fork")
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
            if g.id in state:
                # Com Enabler ativo, o optiscaler.ini pertence ao OptiScaler
                # embutido dele — não reconfigurar por cima (evita conflito).
                if state[g.id].get("enabler"):
                    return {"applied": True, "cached": True, "decision": p.decision,
                            "reconfigured": False, "enabler": True}
                # já otimizado: ainda assim re-aplica overrides (perfis evoluem)
                ok = reconfigure_optiscaler(g, p)
                return {"applied": True, "cached": True, "decision": p.decision,
                        "reconfigured": ok}
            if p.decision == "NOOP":
                return {"applied": False, "noop": True, "reason": p.reason}
            r = _apply_layers(g, p, set())
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
                _save_state(state)
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
        if prev:
            if p.decision != "NOOP":
                if not dry_run:
                    reconfigure_optiscaler(g, p)
                entry["notes"].append(
                    "já otimizado ✓" if not dry_run else "já otimizado ✓ (dry-run)")
                entry["applied"] = True
            else:
                entry["notes"].append(f"registrado, sem ação: {p.reason}")
                entry["applied"] = False
        elif auto_apply and p.decision != "NOOP":
            if dry_run:
                entry["applied"] = True
                entry["notes"] = [f"dry-run: instalaria {' + '.join(p.layers)}"]
                results.append(entry)
                continue
            # ATENÇÃO: `layers_done` precisa ser POR JOGO. Antes era compartilhado
            # entre iterações e fazia o 2º jogo em diante pular todas as camadas.
            r = _apply_layers(g, p, set())
            entry["applied"] = r["ok"]
            entry["notes"].extend(r["notes"])
            if r["ok"]:
                files = [p.dll_name, "OptiScaler.ini", "dlssg_sm86.ini"]
                if p.dll_name != "version.dll":
                    files.append("version.dll")
                if p.layers and "DLSSNR_FORK" in p.layers:
                    files += ["nvngx_dlssnr.dll", "dxgi.dll"]
                state[g.id] = {
                    "folder": g.folder, "title": g.title, "decision": p.decision,
                    "installed_files": files,
                    "installed_dirs": (["OptiScaler", "Licenses_DLSSNR"]
                                       if "DLSSNR_FORK" in p.layers
                                       else ["D3D12_Optiscaler", "Licenses"]),
                }
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
