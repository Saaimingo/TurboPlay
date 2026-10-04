"""TurboPlay — tipos centrais."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path


class API(str, Enum):
    DX12 = "DX12"
    DX11 = "DX11"
    DX10 = "DX10"
    DX9 = "DX9"
    VULKAN = "VULKAN"
    OPENGL = "OPENGL"
    UNKNOWN = "UNKNOWN"


class Upscaler(str, Enum):
    DLSS2 = "DLSS2"
    XESS = "XeSS"
    FSR2 = "FSR2"
    NONE = "NONE"


class Source(str, Enum):
    STEAM = "steam"
    SAMBOX = "sambox"
    CUSTOM = "custom"
    XBOX = "xbox"          # Game Pass Ultimate / Microsoft Store (MSIX)
    EPIC = "epic"
    GOG = "gog"


@dataclass
class Game:
    id: str
    title: str
    exe_path: str
    folder: str
    source: str
    # launcher: caminho que o jogador usa (exe, .bat, steam://)
    launch_path: str = ""
    steam_appid: str = ""
    # preenchido pelo classificador
    api: str = API.UNKNOWN.value
    upscaler: str = Upscaler.NONE.value
    fg_native: bool = False
    anticheat: bool = False
    ac_names: list[str] = field(default_factory=list)
    pe_bits: int = 0
    imports: list[str] = field(default_factory=list)
    # MSIX/Store: pasta assinada e bloqueada (WindowsApps). Injeção quebra o
    # pacote — o jogo detecta arquivo extra e não abre. Sempre NOOP.
    protected_install: bool = False
    # a pasta do jogo aceita escrita? (testado de verdade, não presumido)
    writable: bool = True
    # motivo pelo qual não é otimizável (vai direto pro reason do perfil)
    blocked_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Profile:
    """Stack decidida para um jogo."""
    game_id: str
    decision: str          # ex.: "MFG_NVIDIA", "OPTISCALER_ONLY", "NOOP"
    reason: str            # explicação legível
    layers: list[str] = field(default_factory=list)
    dll_name: str = ""     # nome do hook (winmm/dxgi/version)
    ini_overrides: dict = field(default_factory=dict)
    files_to_remove: list[str] = field(default_factory=list)
    settings_xml_api: str = ""  # força API no settings.xml (ex.: kSettingAPI_DX12)

    def to_dict(self) -> dict:
        return asdict(self)
