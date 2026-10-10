"""TurboPlay — CLI de orquestração.

Uso:
  python -m src.turboplay scan              # lista jogos; pode testar escrita e extrair fork RAR em cache local
  python -m src.turboplay scan --json       # saída machine-readable
  python -m src.turboplay apply             # aplica automaticamente nos jogos
  python -m src.turboplay rollback --all    # reverte tudo
  python -m src.turboplay watch             # modo residente
"""
from __future__ import annotations

import argparse
import json
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

from .applier import verify_fork_integrity
from .pipeline import rollback_all, run_full
from .profiles import detect_gpu
from .providers import scan_all, provider_summary
from .classifier import classify
from .profiles import decide


def cmd_scan(args: argparse.Namespace) -> int:
    gpu = detect_gpu()
    print(f"GPU: {gpu['name']}  (vendor={gpu['vendor']}, série={gpu.get('series', '?')}, driver={gpu['driver']})")
    ok, why = verify_fork_integrity()
    print(f"Stack DLSS5+MFG: {'PRONTA' if ok else 'INDISPONÍVEL'} — {why}")
    print()
    games = [classify(g) for g in scan_all()]
    if not games:
        print("Nenhum jogo encontrado.")
        return 1
    rows = []
    for g in games:
        p = decide(g, gpu)
        rows.append({
            "title": g.title, "source": g.source, "api": g.api,
            "upscaler": g.upscaler, "fg_native": g.fg_native,
            "anticheat": g.anticheat, "decision": p.decision,
            "reason": p.reason, "layers": p.layers,
            "writable": g.writable, "protected": g.protected_install,
            "exe": g.exe_path,
        })
    prov = provider_summary(games)
    if args.json:
        print(json.dumps({"gpu": gpu, "stack_ok": ok, "providers": prov,
                          "games": rows}, indent=2, ensure_ascii=False))
    else:
        print("Provedores: " + " · ".join(f"{k}={v}" for k, v in prov.items()))
        print()
        for r in rows:
            flags = (f"{r['api']} | up={r['upscaler']} | "
                     f"fg={'sim' if r['fg_native'] else 'não'} | "
                     f"ac={'SIM' if r['anticheat'] else '-'}")
            if r["protected"]:
                flags += " | PROTEGIDO"
            elif not r["writable"]:
                flags += " | SEM ESCRITA"
            print(f"[{r['source']:7}] {r['title']}")
            print(f"          {flags}")
            print(f"          → {r['decision']}: {r['reason']}")
            if r["layers"]:
                print(f"            camadas: {' + '.join(r['layers'])}")
            print()
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    if args.dry_run:
        print("=== DRY-RUN: sem instalação nem gravação do estado; "
              "a descoberta ainda cria/remove probe transitório de permissão ===\n")
        result = run_full(auto_apply=True, dry_run=True)
    else:
        ok, why = verify_fork_integrity()
        if not ok:
            print(f"✗ Stack DLSS5+MFG indisponível: {why}")
            print("  Baixe/extraia o fork em _downloads\\optiscaler_dlssnr_087\\ "
                  "e o Streamline em _downloads\\streamline-sdk-2.14.1\\")
            return 2
        result = run_full(auto_apply=True)
    gpu = result["gpu"]
    print(f"GPU: {gpu['name']}")
    for r in result["games"]:
        status = "✓" if r["applied"] else ("intocável" if r["decision"] == "NOOP" else "—")
        print(f"  [{status}] {r['title']}: {r['decision']}")
        for n in r["notes"]:
            print(f"        {n}")
    s = result["summary"]
    print(f"\n{s['otimizados']} otimizado(s) / {s['total']} jogo(s) / {s['intocaveis']} intocável(is)")
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    n = rollback_all()
    print(f"{n} jogo(s) revertido(s) ao estado original.")
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    """Modo residente: otimiza jogos novos sozinho, sem UI."""
    from .notify import notify
    from .watcher import LibraryWatcher, auto_optimize_new_games
    if not args.silent:
        print("TurboPlay residente — monitorando novos jogos (Ctrl+C para sair)...")
    ok, why = verify_fork_integrity()
    if not ok:
        if not args.silent:
            print(f"⚠ Stack DLSS5+MFG indisponível: {why}")
            print("  O watcher vai rodar, mas sem DLSS 5. Corrija o cache para a stack completa.")
    try:
        r = auto_optimize_new_games(dry_run=args.dry_run)
        for title, dec in r["applied"]:
            notify("TurboPlay", f"Novo jogo otimizado: {title} ({dec})")
    except Exception:
        pass
    w = LibraryWatcher(on_change=lambda: auto_optimize_new_games(dry_run=args.dry_run),
                       poll_sec=args.interval)
    try:
        w.loop()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_autostart(args: argparse.Namespace) -> int:
    from . import autostart as A
    if args.action == "on":
        ok = A.set_enabled(True)
    elif args.action == "off":
        ok = A.set_enabled(False)
    else:
        print(A.status_detail())
        return 0
    print("autostart:", "ligado" if (ok and args.action == "on") else
          ("desligado" if args.action == "off" else "FALHOU"))
    print(A.status_detail())
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="turboplay")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser(
        "scan", help="descobre jogos; pode testar escrita nas pastas detectadas e extrair fork RAR em cache local")
    s.add_argument("--json", action="store_true")
    ap_apply = sub.add_parser("apply")
    ap_apply.add_argument("--dry-run", action="store_true",
                          help="sem instalar/salvar estado; descoberta cria/remove probe transitório")
    r = sub.add_parser("rollback")
    r.add_argument("--all", action="store_true")
    w = sub.add_parser("watch")
    w.add_argument("--interval", type=int, default=20)
    w.add_argument("--silent", action="store_true")
    w.add_argument("--once", action="store_true")
    w.add_argument("--dry-run", action="store_true",
                   help="sem instalar/salvar estado; descoberta testa escrita e verificação da stack pode extrair fork RAR em cache local")
    au = sub.add_parser("autostart", help="liga/desliga o início automático (pasta Inicializar)")
    au.add_argument("action", choices=["on", "off", "status"])
    args = ap.parse_args(argv)
    if args.cmd == "scan":
        return cmd_scan(args)
    if args.cmd == "apply":
        return cmd_apply(args)
    if args.cmd == "rollback":
        return cmd_rollback(args)
    if args.cmd == "watch":
        return cmd_watch(args)
    if args.cmd == "autostart":
        return cmd_autostart(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
