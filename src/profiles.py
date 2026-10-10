"""TurboPlay — motor de perfis: GPU + classificação → stack de camadas.

Matriz de decisão (docs/ARQUITETURA.md §3), atualizada com a descoberta de
22/09: a stack que realmente entrega **DLSS 5 (Neural Render) + MFG** na série
20/30/40 é o fork OptiScaler-DLSSNR + proxy SM86, e não o OptiScaler classic.

Ordem de decisão (primeira que casa vence):
  1. anti-cheat                      → NOOP (segurança absoluta, D2)
  2. instalação bloqueada (MSIX)     → NOOP (quebraria o pacote assinado)
  3. pasta sem escrita                → NOOP (explicar, não fingir)
  4. API != DX12                      → NOOP (rota alternativa futura)
  5. NVIDIA série 20/30/40 + DX12    → DLSSNR_FORK + SM86  ← o que o Saimon pediu
  6. NVIDIA série 50 + DX12          → MFG nativo já existe
  7. AMD/Intel                       → OptiScaler FSR/XeSS-FG
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .models import Game, Profile

# Executáveis de RE Engine pré-DLSS3: nascidos antes de existir FG nativa.
# Ter os DLLs do DLSS-G na pasta não significa que o jogo os chame.
_REENGINE_PRE_FG_EXES = {"re2.exe", "re3.exe", "re7.exe", "re8.exe",
                         "dmc5.exe"}

# ── componentes da stack DLSS5+MFG (validados em 22/09, decisão D12) ─────────
FORK_LAYER = "DLSSNR_FORK"
FORK_CACHE = "optiscaler_dlssnr_087"      # fork v0.8.7 (zip standard, hash pinado)
STREAMLINE_CACHE = "streamline-sdk-2.14.1"  # NVIDIA RTX oficial, 6 DLLs


def detect_gpu() -> dict:
    """Detecta vendor/modelo da GPU principal (sem dependências)."""
    info = {"vendor": "unknown", "name": "unknown", "driver": "", "series": 0}
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=15,
        )
        if out.returncode == 0 and out.stdout.strip():
            name, _, driver = out.stdout.strip().partition(", ")
            info.update(vendor="nvidia", name=name.strip(), driver=driver.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    if info["vendor"] == "unknown":
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_VideoController | Select-Object -First 1 -ExpandProperty Name"],
                capture_output=True, text=True, timeout=20,
            )
            name = out.stdout.strip()
            if name:
                info["name"] = name
                low = name.lower()
                if "radeon" in low or "amd" in low:
                    info["vendor"] = "amd"
                elif "arc" in low or "intel" in low:
                    info["vendor"] = "intel"
        except (OSError, subprocess.TimeoutExpired):
            pass
    if info["vendor"] == "nvidia":
        import re as _re
        m = _re.search(r"RTX\s*(\d{4})", info["name"])
        if m:
            info["series"] = int(m.group(1)[0]) * 10
    return info


# Overrides do fork por seção (sintaxe do fork v0.8.7 — NÃO do OptiScaler 0.9.4).
# Validado no RDR2 em 22/09 pelos logs do jogo rodando.
_FORK_INI = {
    "Dx12Upscaler": "dlss",
    "FrameGen/Enabled": "true",
    "FrameGen/FGInput": "upscaler",
    "FrameGen/FGOutput": "dlssg",     # Streamline oficial gera o frame
    "FrameGen/FGNvngxReplacement": "None",
    "DLSSG/InterpolationCount": "1",  # 2x total; 2/3 => 3x/4x
    "V-Sync/OverrideVsync": "true",
    "V-Sync/ForceVsync": "false",
    "Menu/OverlayMenu": "true",      # RE Engine antigo: auto cai no overlay velho e o Insert não abre (achado 09/10 com RE3)
    "Menu/UseHQFont": "false",
    "Log/LogToFile": "true",
    "Log/LogLevel": "2",
    "DlssNr/Enabled": "true",
    "DlssNr/RunBeforeSR": "true",     # pre-SR: 1 passe
    "DlssNr/Passes": "1",
    "DlssNr/WorkingScale": "1.0",
    # ── ponte do FG: as duas chaves abaixo são a correção documentada pelo
    # próprio fork (docs/RTX40-MFG.md) para games que não satisfazem os
    # requisitos de apresentação do Streamline.
    # Sem elas o FG é recusado com 0xbad0000b (NGX recusa a arquitetura) e o
    # log enche de "GetCurrentBackBufferIndex API must be used every frame".
    "NvApi/DisableFlipMetering": "true",   # desliga o metering que exige flip
    "ForceReflex": "2",                    # 0=seguir o jogo, 1=desligar, 2=LIGAR
}

# Perfis por jogo que exigem ajustes além do fork.
_GAME_OVERRIDES: dict[str, dict] = {
    "rdr2.exe": {
        "dll_name": "dxgi.dll",
        "ini_overrides": {"Spoofing/Dxgi": "false"},  # wiki RDR2: spoofing cria artefato
        "files_to_remove": ["fakenvapi.dll",
                            "dlssg_to_fsr3_amd_is_better.dll"],  # conflito de FG
        "settings_xml_api": "kSettingAPI_DX12",       # Vulkan não tem FG (D8)
        "notes": "DX12 obrigatório; stack fork DLSSNR + SM86 (D12)",
    },
    "re2.exe": {"dll_name": "dxgi.dll"},
    "re3.exe": {"dll_name": "dxgi.dll"},
    "re4.exe": {"dll_name": "dxgi.dll"},
}

# Fallback para quando o fork NÃO está disponível (cache ausente): OptiScaler
# classic com FSR3-FG. Ainda entrega frame generation, só não DLSS 5.
_CLASSIC_INI = {
    "FrameGen/Enabled": "true",
    "FrameGen/FGInput": "upscaler",
    "FrameGen/FGOutput": "fsrfg",
    "V-Sync/OverrideVsync": "true",
    "V-Sync/ForceVsync": "false",
}


def _mk_profile(game: Game, decision: str, reason: str,
                layers: list[str] | None = None, **kw) -> Profile:
    ov = _GAME_OVERRIDES.get(game.exe_path.lower().rsplit("\\", 1)[-1], {})
    ini = dict(kw.get("ini_overrides") or {})
    for k, v in (ov.get("ini_overrides") or {}).items():
        ini.setdefault(k, v)
    return Profile(
        game_id=game.id, decision=decision, reason=reason,
        layers=layers or [], dll_name=ov.get("dll_name", kw.get("dll_name", "dxgi.dll")),
        ini_overrides=ini,
        files_to_remove=ov.get("files_to_remove", []),
        settings_xml_api=ov.get("settings_xml_api", ""),
    )


def decide(game: Game, gpu: dict) -> Profile:
    """Aplica a matriz de decisão. Retorna sempre um Profile (nunca levanta)."""
    # 1. segurança absoluta (D2)
    if game.anticheat:
        return _mk_profile(
            game, "NOOP",
            f"anti-cheat detectado ({', '.join(game.ac_names)}) — intocável")

    # 2. instalação assinada e bloqueada (Game Pass / MS Store)
    if game.protected_install:
        return _mk_profile(game, "NOOP",
                           game.blocked_reason or "instalação protegida — intocável")

    # 3. pasta sem escrita: detectamos, não fingimos
    if not game.writable:
        return _mk_profile(
            game, "NOOP",
            "pasta do jogo não aceita escrita (sem permissão de admin) — "
            "rode o TurboPlay como administrador ou mova o jogo")

    if game.pe_bits != 64:
        return _mk_profile(game, "NOOP", "executável não é x64")

    # 4. só DX12 tem rota injetável honesta hoje
    if game.api != "DX12":
        return _mk_profile(
            game, "NOOP",
            f"API {game.api} não suporta DLSS/MFG injetável (rota alternativa futura)")

    # 5. NVIDIA série 20/30/40: aqui mora o DLSS5 + MFG
    if gpu["vendor"] != "nvidia":  # rota AMD/Intel permanece a mesma
        return _mk_profile(
            game, "OPTISCALER_XEFG",
            f"GPU {gpu['name']}: OptiScaler com frame gen FSR/XeSS",
            layers=["OptiScaler"])

    series = gpu.get("series", 0)
    if series in (20, 30, 40):
        # Stack única (decisão 09/10, Saimon): fork OptiScaler-DLSSNR
        # (repack comunitário) em TODOS os jogos DX12 da série 20/30/40 —
        # inclusive os com FG nativa. O repack substitui o DLSS-G do jogo
        # com elegância (FGNvngxReplacement) e é o setup que o titular
        # validou manualmente. Antes: jogos com fg_native recebiam só o
        # proxy SM86 (MFG_NATIVE) e ficavam SEM overlay — o Insert nem
        # abria. Com o fork sempre presente, Insert menu + DLSS 5 NR + MFG
        # ficam disponíveis igual ao setup manual.
        #
        # FG Output por tipo de jogo (achado 09/10 com RE3):
        # - RE Engine pré-DLSS3: força FGOutput=fsrfg via OptiFG mesmo se o
        #   classificador detectar DLLs FG embarcadas; esses jogos não chamam
        #   slDLSSGSetState (44 fps medido, zero frames gerados pela rota dlssg).
        # - Outros jogos DX12: mantém FGOutput=dlssg do fork, com ou sem
        #   FG nativa detectada. Não inferir FSR3-FG para esses jogos.
        # OptiFG é experimental segundo a wiki do OptiScaler; HUDFix pode ser
        # necessário em jogos com HUD complexo.
        ini = dict(_FORK_INI)
        # RE Engine antigo (RE2/RE3/RE7/RE8/DMC5): o jogo EMBARCA os DLLs do
        # DLSS-G, então o classificador reporta fg_native=True — mas o jogo
        # NUNCA chama slDLSSGSetState (jogos pré-DLSS3). Log do RE3 em 09/10
        # provou: zero chamadas, 44 fps. Força a rota OptiFG (FSR3-FG) sempre,
        # independente do fg_native e com prioridade sobre o dlssg herdado.
        ex_lower = Path(game.exe_path).name.lower()
        if ex_lower in _REENGINE_PRE_FG_EXES:
            ini["FrameGen/FGOutput"] = "fsrfg"
            ini["FrameGen/FGNvngxReplacement"] = "FFX"
            ini["OptiFG/HUDFix"] = "true"
            fg_route = "FSR3-FG via OptiFG (RE Engine pré-DLSS3)"
        else:
            fg_route = "FGOutput=dlssg"
        return _mk_profile(
            game, "DLSS5_MFG",
            f"DLSS 5 Neural Render + MFG NVIDIA ({fg_route}) na série {series}",
            layers=[FORK_LAYER, "SM86"],
            ini_overrides=ini)

    if series >= 50:
        return _mk_profile(
            game, "MFG_NATIVE",
            f"série {series}: MFG e DLSS 5 já nativos do driver — só falta o jogo suportar",
            layers=[], dll_name="dxgi.dll")

    return _mk_profile(
        game, "OPTISCALER_ONLY",
        f"GPU {gpu['name']} sem perfil DLSS 5: OptiScaler com FG FSR3",
        layers=["OptiScaler"], ini_overrides=_CLASSIC_INI)