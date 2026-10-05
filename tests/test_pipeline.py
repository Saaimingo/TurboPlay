"""Testes do TurboPlay — sem pytest, sem dependências (D4).

Rodar:  python -m tests.run_tests        (ou python tests/run_tests.py)

Cobrem os defeitos achados na revisão de 04/10/2026:
  · run_full instalava camadas só no PRIMEIRO jogo (layers_done compartilhado)
  · jogo com anti-cheat nunca pode ser tocado
  · instalação MSIX/Store precisa ser NOOP, não injetada
  · executável de emulador não pode entrar na fila de otimização
  · série 20/30/40 NVIDIA deve receber a stack DLSS 5 + MFG
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src import providers, profiles
from src.models import Game, Profile

_results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    _results.append((name, bool(cond), detail))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def fake_game(**kw) -> Game:
    base = dict(id="tp_test", title="Jogo", exe_path=r"C:\j\Jogo.exe",
                folder=r"C:\j", source="steam")
    base.update(kw)
    g = Game(**base)
    return g


# ── 1. o bug do pipeline: cada jogo recebe sua própria stack ─────────────────


def test_pipeline_layers_per_game() -> None:
    import src.pipeline as P
    calls: list[tuple[str, str]] = []
    P.apply_sm86 = lambda g, p: (calls.append(("SM86", g.title)), True)[1]
    P.apply_optiscaler = lambda g, p: (calls.append(("OptiScaler", g.title)), True)[1]
    P.try_install_enabler = lambda g: (calls.append(("Enabler", g.title)), (True, "ok"))[1]
    P.reconfigure_optiscaler = lambda g, p: True
    P.detect_gpu = lambda: {"vendor": "nvidia", "name": "RTX 3060", "driver": "", "series": 30}
    P._load_state = lambda: {}
    P._save_state = lambda s: None

    def mk(i):
        return Game(id=f"g{i}", title=f"Jogo {i}", exe_path=fr"C:\j{ i}\Game{i}.exe",
                    folder=fr"C:\j{i}", source="steam")
    P.scan_all = lambda *a, **k: [mk(1), mk(2), mk(3)]
    P.classify = lambda g: g

    # perfil que instala 2 camadas, para o bug aparecer com clareza
    P.decide = lambda g, gpu: Profile(
        game_id=g.id, decision="DLSS5_MFG", reason="teste",
        layers=["SM86", "OptiScaler"], dll_name="version.dll")

    P.run_full(auto_apply=True)
    titles_with_sm86 = {t for lay, t in calls if lay == "SM86"}
    check("pipeline: TODOS os jogos recebem SM86 (bug do layers_done)",
          titles_with_sm86 == {"Jogo 1", "Jogo 2", "Jogo 3"},
          f"receberam={sorted(titles_with_sm86)}")


# ── 2. segurança: anti-cheat intocável ──────────────────────────────────────


def test_anticheat_noop() -> None:
    g = fake_game(anticheat=True, ac_names=["BEService.exe"], pe_bits=64)
    p = profiles.decide(g, {"vendor": "nvidia", "name": "RTX 3060", "series": 30})
    check("anti-cheat → NOOP", p.decision == "NOOP" and not p.layers, p.decision)
    check("anti-cheat → motivo cita o anti-cheat",
          "anti-cheat" in p.reason.lower(), p.reason[:40])


# ── 3. Game Pass / MSIX é NOOP, nunca injetado ───────────────────────────────


def test_xbox_protected() -> None:
    g = fake_game(source="xbox", protected_install=True, writable=False,
                  blocked_reason="pacote MSIX assinado", pe_bits=64, api="DX12")
    p = profiles.decide(g, {"vendor": "nvidia", "name": "RTX 3060", "series": 30})
    check("Game Pass/MSIX → NOOP", p.decision == "NOOP", p.decision)
    check("Game Pass/MSIX → nenhuma camada", p.layers == [], str(p.layers))
    check("Game Pass/MSIX → motivo explica", "MSIX" in p.reason, p.reason[:40])


# ── 4. pasta sem escrita é explicada, não ignorada ───────────────────────────


def test_not_writable() -> None:
    g = fake_game(writable=False, pe_bits=64, api="DX12")
    p = profiles.decide(g, {"vendor": "nvidia", "name": "RTX 3060", "series": 30})
    check("sem escrita → NOOP", p.decision == "NOOP", p.decision)
    check("sem escrita → motivo menciona permissão",
          "escrita" in p.reason.lower() or "admin" in p.reason.lower(), p.reason[:40])


# ── 5. NVIDIA série 30 recebe a stack DLSS 5 + MFG ───────────────────────────


def test_series30_gets_dlss5_mfg() -> None:
    g = fake_game(pe_bits=64, api="DX12", upscaler="DLSS2", fg_native=False)
    p = profiles.decide(g, {"vendor": "nvidia", "name": "RTX 3060", "series": 30})
    check("série 30 → decisão DLSS5_MFG", p.decision == "DLSS5_MFG", p.decision)
    check("série 30 → fork DLSSNR + SM86", p.layers == ["DLSSNR_FORK", "SM86"], str(p.layers))
    check("série 30 → NR habilitada",
          p.ini_overrides.get("DlssNr/Enabled") == "true", str(p.ini_overrides.get("DlssNr/Enabled")))
    check("série 30 → FG saída dlssg",
          p.ini_overrides.get("FrameGen/FGOutput") == "dlssg", str(p.ini_overrides.get("FrameGen/FGOutput")))


def test_native_fg_not_overridden_by_fork() -> None:
    """Jogo com FG nativa nao pode receber o fork por cima.

    Era o que aconteceria com The Last of Us II Remastered: o jogo ja tem
    DLSS-G funcionando, e enfiar o OptiScaler/dxgi.dll encima arriscava
    derrubar o FG nativo. Aqui so entra o proxy SM86.
    """
    g = fake_game(pe_bits=64, api="DX12", upscaler="DLSS2", fg_native=True)
    p = profiles.decide(g, {"vendor": "nvidia", "name": "RTX 3060", "series": 30})
    check("FG nativa (série 30) → MFG_NATIVE, não DLSS5_MFG",
          p.decision == "MFG_NATIVE", p.decision)
    check("FG nativa → só proxy SM86, sem fork",
          p.layers == ["SM86"], str(p.layers))
    check("FG nativa → não escreve OptiScaler.ini do fork",
          not p.ini_overrides, str(p.ini_overrides))
    check("FG nativa → usa o slot version.dll",
          p.dll_name == "version.dll", p.dll_name)

    # sem FG nativa continua sendo a rota do fork
    g2 = fake_game(pe_bits=64, api="DX12", upscaler="DLSS2", fg_native=False)
    p2 = profiles.decide(g2, {"vendor": "nvidia", "name": "RTX 3060", "series": 30})
    check("sem FG nativa → continua DLSS5_MFG + fork",
          p2.decision == "DLSS5_MFG" and p2.layers == ["DLSSNR_FORK", "SM86"],
          f"{p2.decision} {p2.layers}")


def test_series50_native() -> None:
    g = fake_game(pe_bits=64, api="DX12")
    p = profiles.decide(g, {"vendor": "nvidia", "name": "RTX 5090", "series": 50})
    check("série 50 → MFG nativo, sem injeção", p.decision == "MFG_NATIVE", p.decision)
    check("série 50 → nenhuma camada", p.layers == [], str(p.layers))


def test_amd_gets_optiscaler() -> None:
    g = fake_game(pe_bits=64, api="DX12")
    p = profiles.decide(g, {"vendor": "amd", "name": "RX 7800", "series": 0})
    check("AMD → OptiScaler XeFG", p.decision == "OPTISCALER_XEFG", p.decision)


def test_non_dx12_noop() -> None:
    g = fake_game(pe_bits=64, api="DX11")
    p = profiles.decide(g, {"vendor": "nvidia", "name": "RTX 3060", "series": 30})
    check("DX11 → NOOP honesto", p.decision == "NOOP", p.decision)


# ── 6. emulador/frontend nunca entra na fila ────────────────────────────────


def test_emulator_exe_filtered() -> None:
    check("DuckStation filtrado", providers.is_tool_exe(r"D:\x\duckstation-qt-x64-ReleaseLTCG.exe"))
    check("RetroArch filtrado", providers.is_tool_exe(r"D:\x\retroarch.exe"))
    check("Jogo real NÃO filtrado", not providers.is_tool_exe(r"D:\x\RDR2.exe"))
    check("jogo genérico NÃO filtrado", not providers.is_tool_exe(r"D:\x\Cyberpunk2077.exe"))


# ── 7. teste real de escrita (o que decide se dá para otimizar) ──────────────


def test_is_writable_real() -> None:
    with tempfile.TemporaryDirectory(prefix="tp_w_") as d:
        check("pasta comum → gravável", providers.is_writable(d))
        check("arquivo como pasta → não gravável", not providers.is_writable(str(Path(d) / "x")))


# ── 8. signature do watcher pega evento perdido ─────────────────────────────


def test_watcher_signature_catches_subdir() -> None:
    from src.watcher import _signature, _count_items
    import time
    with tempfile.TemporaryDirectory(prefix="tp_sig_") as d:
        root = Path(d) / "roms"
        ps1 = root / "ps1"
        ps1.mkdir(parents=True)
        before = _signature([root])
        time.sleep(1.1)
        (ps1 / "jogo.ps1").write_text("x")
        after = _signature([root])
        check("watcher: ROM nova em subpasta muda a assinatura",
              before != after, "antes!=depois" if before != after else "PERDEU o evento")
        check("watcher: contagem sobe", _count_items([root]) >= 2)


# ── 9. estado de geração antiga NÃO pode enganar o código novo ────────────────


def test_stale_state_forces_reapply() -> None:
    """Causa do RDR2 ficar sem fork em 04/10: installed.json do v1.6 dizia
    'já otimizado' e o código novo aceitava, sem reinstalar a stack."""
    from src.applier import is_state_current, STATE_SCHEMA
    p = profiles.decide(fake_game(pe_bits=64, api="DX12"),
                        {"vendor": "nvidia", "name": "RTX 3060", "series": 30})

    # entrada escrita pelo v1.6: sem schema, camadas antigas, slot winmm
    stale = {"folder": r"C:\j", "title": "Jogo", "decision": "MFG_NVIDIA",
             "installed_files": ["winmm.dll", "OptiScaler.ini", "version.dll"],
             "installed_dirs": ["D3D12_Optiscaler", "Licenses"]}
    ok, why = is_state_current(stale, p)
    check("estado v1.6 (sem schema) →considered desatualizado", not ok, why)

    # entrada nova mas com camadas erradas
    wrong_layers = {"schema": STATE_SCHEMA, "layers": ["OptiScaler"],
                    "dll_name": "dxgi.dll"}
    ok2, why2 = is_state_current(wrong_layers, p)
    check("camadas divergentes → desatualizado", not ok2, why2[:40])

    # entrada nova e coerente: aí sim pode pular
    from src.applier import state_entry_for
    g = fake_game(pe_bits=64, api="DX12")
    fresh = state_entry_for(g, p)
    ok3, why3 = is_state_current(fresh, p)
    check("estado coerente → pode pular", ok3, why3)
    check("estado novo grava o schema", fresh.get("schema") == STATE_SCHEMA,
          str(fresh.get("schema")))
    check("estado novo registra as camadas", fresh.get("layers") == p.layers,
          str(fresh.get("layers")))


def test_component_version_bump_reinstalls() -> None:
    """Atualizar o fork (0.8.7 -> 0.8.91) tem que reinstalar o componente.

    Sem isso o 'apply' reaproveita o estado e o jogo continua com a DLL antiga,
    que era exatamente o risco do D3 ('atualização de componente = PR').
    """
    from src.applier import is_state_current, state_entry_for, FORK_VERSION
    g = fake_game(pe_bits=64, api="DX12")
    p = profiles.decide(g, {"vendor": "nvidia", "name": "RTX 3060", "series": 30})
    fresh = state_entry_for(g, p)
    check("estado registra a versao do fork", fresh.get("fork_version") == FORK_VERSION,
          str(fresh.get("fork_version")))
    ok, _ = is_state_current(fresh, p)
    check("estado na versao atual → pode pular", ok)

    older = dict(fresh, fork_version="0.8.7")
    ok2, why2 = is_state_current(older, p)
    check("fork mais antigo → reinstalar", not ok2, why2[:46])

    # upgrade que acabou de acontecer: 0.8.7 -> 0.8.91
    if FORK_VERSION == "0.8.91":
        check("upgrade 0.8.7→0.8.91 detectado", not ok2)


def test_launcher_success_returns_no_error() -> None:
    """Lançar um jogo Steam NÃO pode devolver erro.

    Causa do popup 'O Windows não pode localizar "\\\\"' e da mensagem
    'Não consegui abrir': o ramo Steam devolvia (None, url) — a URL ia como
    erro, então a GUI acusava falha, e `cmd /c start` com protocolo quebrava.
    """
    import src.launcher as L
    g = Game(id="x", title="RE1", exe_path=r"C:\j\bhd.exe", folder=r"C:\j",
             source="steam", launch_path="steam://rungameid/304240",
             steam_appid="304240")
    calls: list[list] = []
    original = L.subprocess.Popen
    L.subprocess.Popen = lambda a, **k: calls.append(a) or None
    try:
        popen, err = L.launch(g)
    finally:
        L.subprocess.Popen = original
    check("Steam: sucesso devolve erro VAZIO", err == "", repr(err))
    check("Steam: usa -applaunch, nao o protocolo quebrado",
          bool(calls) and calls[0][1:] == ["-applaunch", "304240"],
          str(calls[0][1:]) if calls else "nenhuma chamada")
    check("Steam: popen e None (quem abre e o cliente)", popen is None)


def main() -> int:
    print("TurboPlay — suite de testes\n")
    for fn in (test_pipeline_layers_per_game, test_anticheat_noop, test_xbox_protected,
               test_not_writable, test_series30_gets_dlss5_mfg, test_series50_native,
               test_amd_gets_optiscaler, test_non_dx12_noop, test_emulator_exe_filtered,
               test_is_writable_real, test_watcher_signature_catches_subdir,
               test_stale_state_forces_reapply, test_component_version_bump_reinstalls,
               test_launcher_success_returns_no_error, test_native_fg_not_overridden_by_fork):
        print(f"[{fn.__name__}]")
        fn()
        print()
    total = len(_results)
    passed = sum(1 for _, ok, _ in _results if ok)
    print(f"RESULTADO: {passed}/{total} PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())