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

from src import covers, providers, profiles
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


def test_native_fg_also_uses_dlss5_mfg() -> None:
    """RTX 20/30/40 recebe DLSS 5 + MFG com ou sem FG nativa no jogo."""
    g = fake_game(pe_bits=64, api="DX12", upscaler="DLSS2", fg_native=True)
    p = profiles.decide(g, {"vendor": "nvidia", "name": "RTX 3060", "series": 30})
    check("FG nativa (série 30) → DLSS5_MFG",
          p.decision == "DLSS5_MFG", p.decision)
    check("FG nativa → camadas DLSSNR + SM86",
          p.layers == ["DLSSNR_FORK", "SM86"], str(p.layers))
    check("FG nativa → saída DLSSG",
          p.ini_overrides.get("FrameGen/FGOutput") == "dlssg",
          str(p.ini_overrides.get("FrameGen/FGOutput")))
    check("FG nativa → slot padrão dxgi.dll",
          p.dll_name == "dxgi.dll", p.dll_name)
    check("FG nativa: motivo corresponde à saída dlssg",
          p.ini_overrides.get("FrameGen/FGOutput") == "dlssg"
          and "FGOutput=dlssg" in p.reason and "FSR3-FG" not in p.reason,
          p.reason)

    # sem FG nativa continua sendo a rota do fork
    g2 = fake_game(pe_bits=64, api="DX12", upscaler="DLSS2", fg_native=False)
    p2 = profiles.decide(g2, {"vendor": "nvidia", "name": "RTX 3060", "series": 30})
    check("sem FG nativa → DLSS5_MFG + fork",
          p2.decision == "DLSS5_MFG" and p2.layers == ["DLSSNR_FORK", "SM86"],
          f"{p2.decision} {p2.layers}")
    check("sem FG nativa: motivo corresponde à saída dlssg",
          p2.ini_overrides.get("FrameGen/FGOutput") == "dlssg"
          and "FGOutput=dlssg" in p2.reason and "FSR3-FG" not in p2.reason,
          p2.reason)

    re3 = fake_game(exe_path=r"C:\games\re3.exe", fg_native=True,
                    pe_bits=64, api="DX12", upscaler="DLSS2")
    p_re3 = profiles.decide(re3, {"vendor": "nvidia", "name": "RTX 3060", "series": 30})
    check("RE3 com FG detectada mantém DLSS5_MFG", p_re3.decision == "DLSS5_MFG",
          p_re3.decision)
    check("RE3 mantém exceção OptiFG/FSR3-FG",
          p_re3.ini_overrides.get("FrameGen/FGOutput") == "fsrfg"
          and "OptiFG" in p_re3.reason,
          p_re3.reason)


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


def test_is_writable_preserves_existing_probe_name() -> None:
    """Um arquivo com nome legado não pode ser sobrescrito nem apagado."""
    with tempfile.TemporaryDirectory(prefix="tp_w_collision_") as d:
        folder = Path(d)
        sentinel = folder / ".tp_write_probe.tmp"
        sentinel.write_text("owned data", encoding="ascii")

        writable = providers.is_writable(d)
        preserved = sentinel.is_file() and sentinel.read_text(encoding="ascii") == "owned data"
        names_after = {path.name for path in folder.iterdir()}

        check("probe preserva arquivo preexistente", writable and preserved,
              f"gravavel={writable}, preservado={preserved}")
        check("probe temporário próprio é removido", names_after == {sentinel.name},
              str(sorted(names_after)))


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


def test_classifier_ignores_our_own_streamline_dll() -> None:
    """O classificador NÃO pode contar o sl.dlss_g.dll que nós instalamos.

    Bug autoalimentado: instalar o fork cria
    OptiScaler/streamline/sl.dlss_g.dll, e o rglob via achava e declarava
    "FG nativa". Aí o decide() parava de reinstalar o fork.
    """
    import tempfile, shutil
    from src.classifier import classify
    from src.models import Game as _G
    with tempfile.TemporaryDirectory(prefix="tp_cls_") as d:
        root = Path(d)
        (root / "OptiScaler" / "streamline").mkdir(parents=True)
        (root / "OptiScaler" / "streamline" / "sl.dlss_g.dll").write_bytes(b"x")
        g = classify(_G(id="t", title="Jogo", exe_path=str(root / "jogo.exe"),
                        folder=str(root), source="steam", pe_bits=64, api="DX12"))
        check("sl.dlss_g.dll NOSSO não conta como FG nativa",
              g.fg_native is False, str(g.fg_native))

        # mas o do jogo, na raiz, conta
        (root / "sl.dlss_g.dll").write_bytes(b"x")
        g2 = classify(_G(id="t", title="Jogo", exe_path=str(root / "jogo.exe"),
                         folder=str(root), source="steam", pe_bits=64, api="DX12"))
        check("sl.dlss_g.dll DO JOGO conta como FG nativa",
              g2.fg_native is True, str(g2.fg_native))


def test_cover_cache_accepts_supported_images_only() -> None:
    """Fixtures reais passam; imagens PNG/GIF truncadas ou corrompidas falham."""
    import tempfile
    from PIL import Image

    with tempfile.TemporaryDirectory(prefix="tp_cover_") as d:
        root = Path(d)
        cache = root / "cache"
        png = root / "capa.png"
        Image.new("RGB", (2, 2), (30, 80, 120)).save(png, format="PNG")
        target = covers.set_cover("tp_game-1", png, cache)
        check("fixture PNG válida copiada para cache por jogo",
              target.exists() and target.read_bytes() == png.read_bytes(), str(target))
        check("PNG válido resolvido pelo id correto",
              covers.get_cover("tp_game-1", cache) == target, str(target))

        gif = root / "capa.gif"
        Image.new("RGB", (3, 2), (120, 50, 20)).save(gif, format="GIF")
        gif_target = covers.set_cover("tp_game-2", gif, cache)
        check("fixture GIF válida copiada e resolvida",
              gif_target.exists() and covers.get_cover("tp_game-2", cache) == gif_target,
              str(gif_target))

        bad = root / "nao-imagem.png"
        bad.write_bytes(b"conteudo")
        malformed = [("PNG sem imagem", bad)]
        truncated_png = root / "truncada.png"
        truncated_png.write_bytes(png.read_bytes()[:-8])
        malformed.append(("PNG truncado", truncated_png))
        corrupted_png = root / "corrompida.png"
        corrupted_data = bytearray(png.read_bytes())
        corrupted_data[-15] ^= 0xFF
        corrupted_png.write_bytes(corrupted_data)
        malformed.append(("PNG com dados corrompidos", corrupted_png))

        truncated_gif = root / "truncada.gif"
        truncated_gif.write_bytes(gif.read_bytes()[:-1])
        malformed.append(("GIF truncado", truncated_gif))
        corrupted_gif = root / "corrompida.gif"
        corrupted_data = bytearray(gif.read_bytes())
        corrupted_data[-2] ^= 0xFF
        corrupted_gif.write_bytes(corrupted_data)
        malformed.append(("GIF corrompido", corrupted_gif))
        for index, (label, path) in enumerate(malformed, start=10):
            try:
                covers.set_cover(f"tp_bad-{index}", path, cache)
            except ValueError:
                rejected = True
            else:
                rejected = False
            check(f"{label} rejeitado ao importar", rejected)

        corrupt_cached = cache / "tp_game-1.png"
        corrupt_cached.write_bytes(truncated_png.read_bytes())
        check("capa corrompida no cache não é exibida", covers.get_cover("tp_game-1", cache) is None)

        huge = root / "huge.png"
        Image.new("RGB", (8192, 8192)).save(huge, format="PNG")
        try:
            covers.set_cover("tp_game-3", huge, cache)
        except ValueError:
            huge_image_rejected = True
        else:
            huge_image_rejected = False
        check("imagem com dimensoes excessivas e rejeitada", huge_image_rejected)

        too_large = root / "too-large.png"
        too_large.write_bytes(b"x" * (20 * 1024 * 1024 + 1))
        try:
            covers.set_cover("tp_game-4", too_large, cache)
        except ValueError:
            oversized_rejected = True
        else:
            oversized_rejected = False
        check("arquivo acima do limite e rejeitado", oversized_rejected)

        try:
            covers.get_cover("../escape", cache)
        except ValueError:
            unsafe_id_rejected = True
        else:
            unsafe_id_rejected = False
        check("id de jogo com traversal e rejeitado", unsafe_id_rejected)


def test_cover_fallback_identity_is_stable_and_game_specific() -> None:
    first = covers.fallback_identity("game-a", "Game Alpha")
    repeated = covers.fallback_identity("game-a", "Game Alpha")
    different = covers.fallback_identity("game-b", "Game Beta")
    check("identidade visual genérica é determinística", first == repeated, str(first))
    check("identidades genéricas diferem por jogo", first != different, str(different))


def test_gui_cover_placeholder_renders_without_cover() -> None:
    """A grade consegue renderizar o placeholder da capa sem imagem válida."""
    from unittest.mock import Mock, patch
    import src.gui as gui

    class DummyParent:
        def __init__(self) -> None:
            self.options = {}

        def configure(self, **kwargs) -> None:
            self.options.update(kwargs)

    parent = DummyParent()
    with patch.object(gui.tk, "Label", return_value=Mock()) as label_factory:
        gui.TurboPlayApp._cover_placeholder(None, parent, "game-a", "Game Alpha")
    expected_background, _ = covers.fallback_identity("game-a", "Game Alpha")
    check("placeholder GUI renderiza três rótulos e cor genérica",
          label_factory.call_count == 3 and parent.options.get("bg") == expected_background,
          f"labels={label_factory.call_count}, bg={parent.options.get('bg')}")


def test_gui_cover_dialog_ignores_reentrant_request() -> None:
    """Uma segunda ativação enquanto o seletor está aberto não abre outro."""
    from types import SimpleNamespace
    from unittest.mock import patch
    import src.gui as gui

    app = SimpleNamespace(root=None)
    game = {"title": "Game Alpha"}
    calls = 0

    def fake_open_dialog(**_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            gui.TurboPlayApp._on_choose_cover(app, game)
        return ""

    with patch("tkinter.filedialog.askopenfilename", side_effect=fake_open_dialog):
        gui.TurboPlayApp._on_choose_cover(app, game)

    check("seletor de capa ignora chamada reentrante", calls == 1, f"aberturas={calls}")


def test_gui_cover_dialog_unlocks_after_picker_error() -> None:
    """Uma falha do diálogo não impede uma tentativa posterior."""
    from types import SimpleNamespace
    from unittest.mock import patch
    import src.gui as gui

    app = SimpleNamespace(root=None)
    game = {"title": "Game Alpha"}
    calls = 0

    def fake_open_dialog(**_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("picker failure fixture")
        return ""

    with patch("tkinter.filedialog.askopenfilename", side_effect=fake_open_dialog):
        try:
            gui.TurboPlayApp._on_choose_cover(app, game)
        except RuntimeError as exc:
            error_caught = str(exc) == "picker failure fixture"
        else:
            error_caught = False
        gui.TurboPlayApp._on_choose_cover(app, game)

    check("seletor libera trava após exceção", error_caught and calls == 2,
          f"exceção={error_caught}, aberturas={calls}")


def test_cover_validation_cache_detects_in_place_changes() -> None:
    """A mesma identidade/tamanho/mtime não pode validar bytes alterados."""
    import os
    from unittest.mock import patch
    from PIL import Image

    with tempfile.TemporaryDirectory(prefix="tp_cover_inplace_") as d:
        cache = Path(d)
        path = cache / "tp_inplace.png"
        Image.new("RGB", (2, 2), (60, 90, 120)).save(path, format="PNG")
        covers._VALIDATION_CACHE.pop(path, None)
        check("imagem inicial válida", covers.get_cover("tp_inplace", cache) == path)

        original = path.read_bytes()
        corrupted = bytearray(original)
        corrupted[-15] ^= 0xFF
        before = path.stat()
        with path.open("wb") as stream:
            stream.write(corrupted)
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        after = path.stat()
        same_signature = (before.st_size == after.st_size
                          and before.st_mtime_ns == after.st_mtime_ns
                          and before.st_ino == after.st_ino)

        with patch.object(covers, "_validate_image", wraps=covers._validate_image) as validate:
            result = covers.get_cover("tp_inplace", cache)
        check("alteração in-place preservou assinatura do stat", same_signature)
        check("bytes alterados são revalidados e rejeitados",
              result is None and validate.call_count == 1,
              f"result={result}, validacoes={validate.call_count}")


def test_cover_validation_cache_reuses_unchanged_image() -> None:
    """A grade não decodifica a mesma capa em cada busca/filtro."""
    import os
    from unittest.mock import patch
    from PIL import Image

    with tempfile.TemporaryDirectory(prefix="tp_cover_validation_") as d:
        cache = Path(d)
        path = cache / "tp_cached.png"
        Image.new("RGB", (2, 2), (60, 90, 120)).save(path, format="PNG")
        original_validate = covers._validate_image
        validations = []

        def track_validation(data: bytes, suffix: str):
            validations.append((len(data), suffix))
            return original_validate(data, suffix)

        with patch.object(covers, "_validate_image", side_effect=track_validation):
            first = covers.get_cover("tp_cached", cache)
            second = covers.get_cover("tp_cached", cache)
            reused = first == path and second == path and len(validations) == 1

            before = path.stat()
            replacement = cache / "replacement.png"
            corrupted = bytearray(path.read_bytes())
            corrupted[-15] ^= 0xFF
            replacement.write_bytes(corrupted)
            os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
            replacement_stat = replacement.stat()
            same_stat_except_identity = (
                replacement_stat.st_size == before.st_size
                and replacement_stat.st_mtime_ns == before.st_mtime_ns
                and replacement_stat.st_ino != before.st_ino)
            replacement.replace(path)
            third = covers.get_cover("tp_cached", cache)
            invalidated = (third is None and len(validations) == 2
                           and same_stat_except_identity)

        check("validação é reutilizada para capa sem alteração", reused,
              f"validações={len(validations)}")
        check("alteração do arquivo invalida o cache de validação", invalidated,
              f"validações={len(validations)}")


def test_gui_photo_cache_reuses_and_refreshes_cover() -> None:
    """A GUI reutiliza PhotoImage em filtros e recarrega capa alterada."""
    import os
    from types import SimpleNamespace
    from unittest.mock import patch
    import src.gui as gui

    class DummyImage:
        def width(self) -> int:
            return 100

        def height(self) -> int:
            return 100

        def subsample(self, _x: int, _y: int):
            return self

    with tempfile.TemporaryDirectory(prefix="tp_gui_photo_") as d:
        path = Path(d) / "cover.png"
        path.write_bytes(b"one")
        app = SimpleNamespace(_cover_images={})
        with patch.object(gui.tk, "PhotoImage", side_effect=lambda **_: DummyImage()) as factory:
            first = gui.TurboPlayApp._cover_photo(app, "game-x", path)
            second = gui.TurboPlayApp._cover_photo(app, "game-x", path)
            reused = first is second and factory.call_count == 1

            before = path.stat()
            replacement = Path(d) / "replacement.png"
            replacement.write_bytes(b"two")
            os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
            replacement_stat = replacement.stat()
            same_stat_except_identity = (
                replacement_stat.st_size == before.st_size
                and replacement_stat.st_mtime_ns == before.st_mtime_ns
                and replacement_stat.st_ino != before.st_ino)
            replacement.replace(path)
            third = gui.TurboPlayApp._cover_photo(app, "game-x", path)
            refreshed = (third is not second and factory.call_count == 2
                         and same_stat_except_identity)

        check("PhotoImage é reutilizada sem alteração", reused,
              f"criações={factory.call_count}")
        check("PhotoImage é recarregada após alteração", refreshed,
              f"criações={factory.call_count}")


def test_fallback_to_fsrfg() -> None:
    """Se o gate recusou (0xbad0000b), cai para fsrfg — e é idempotente."""
    import tempfile
    from src.applier import (maybe_fallback_to_fsrfg, fg_gate_failed,
                             _read_ini_value)
    from src.models import Game as _G
    with tempfile.TemporaryDirectory(prefix="tp_fb_") as d:
        root = Path(d)
        logs = root / "dlssg_sm86" / "logs"
        logs.mkdir(parents=True)
        (logs / "backend_999.jsonl").write_text(
            '{"event":"fg_gate_create_feature","status":"0xbad0000b","succeeded":false}',
            encoding="utf-8")
        ini = root / "OptiScaler.ini"
        ini.write_text("[FrameGen]\nEnabled = true\nFGOutput = DLSSG\n",
                       encoding="utf-8")
        check("detecta a recusa nos logs", fg_gate_failed(str(root)) is True)

        g = _G(id="t", title="Jogo", exe_path=str(root / "jogo.exe"),
               folder=str(root), source="steam")
        p = profiles.Profile(game_id=g.id, decision="DLSS5_MFG", reason="",
                             layers=["DLSSNR_FORK", "SM86"], dll_name="dxgi.dll")
        ok, why = maybe_fallback_to_fsrfg(g, p)
        check("fallback aplica", ok is True, why[:40])
        check("INI passa a FSRFG",
              (_read_ini_value(ini, "FrameGen", "FGOutput") or "").lower() == "fsrfg",
              str(_read_ini_value(ini, "FrameGen", "FGOutput")))
        ok2, _ = maybe_fallback_to_fsrfg(g, p)
        check("fallback e idempotente (2a vez nao faz nada)", ok2 is False)

        # se o gate passou, não mexe
        (logs / "backend_998.jsonl").write_text(
            '{"event":"fg_gate_create_feature","status":"0x0","succeeded":true}',
            encoding="utf-8")
        ini.write_text("[FrameGen]\nFGOutput = DLSSG\n", encoding="utf-8")
        ok3, _ = maybe_fallback_to_fsrfg(g, p)
        check("gate OK → nao mexe no INI", ok3 is False)


def main() -> int:
    print("TurboPlay — suite de testes\n")
    for fn in (test_pipeline_layers_per_game, test_anticheat_noop, test_xbox_protected,
               test_not_writable, test_series30_gets_dlss5_mfg, test_series50_native,
               test_amd_gets_optiscaler, test_non_dx12_noop, test_emulator_exe_filtered,
               test_is_writable_real, test_watcher_signature_catches_subdir,
               test_is_writable_preserves_existing_probe_name,
               test_stale_state_forces_reapply, test_component_version_bump_reinstalls,
               test_launcher_success_returns_no_error, test_native_fg_also_uses_dlss5_mfg,
               test_classifier_ignores_our_own_streamline_dll, test_cover_cache_accepts_supported_images_only,
               test_cover_fallback_identity_is_stable_and_game_specific,
               test_gui_cover_placeholder_renders_without_cover,
               test_gui_cover_dialog_ignores_reentrant_request,
               test_gui_cover_dialog_unlocks_after_picker_error,
               test_cover_validation_cache_detects_in_place_changes,
               test_cover_validation_cache_reuses_unchanged_image,
               test_gui_photo_cache_reuses_and_refreshes_cover, test_fallback_to_fsrfg):
        print(f"[{fn.__name__}]")
        fn()
        print()
    total = len(_results)
    passed = sum(1 for _, ok, _ in _results if ok)
    print(f"RESULTADO: {passed}/{total} PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())