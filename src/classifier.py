"""TurboPlay — classificação de jogos: API gráfica, upscaler, FG nativa, anti-cheat."""
from __future__ import annotations

import struct
from pathlib import Path

from .models import API, Game, Upscaler

_API_DLLS = {
    "d3d12.dll": API.DX12, "d3d11.dll": API.DX11, "d3d10_1.dll": API.DX10,
    "d3d10.dll": API.DX10, "d3d9.dll": API.DX9, "vulkan-1.dll": API.VULKAN,
    "opengl32.dll": API.OPENGL,
}
_AC_HINTS = ["battleye", "beservice", "easyanticheat", "eac_", "denuvo",
             "vmp-", "vmprotect", "xigncode", "wellbia", "faceit", "esea",
             "punkbuster", "fairplay"]
_UPSCALER_FILES = {
    "nvngx_dlss.dll": Upscaler.DLSS2,
    "nvngx_dlssd.dll": Upscaler.DLSS2,   # Ray Reconstruction
    "libxess.dll": Upscaler.XESS,
    "ffx_fsr2_api_x64.dll": Upscaler.FSR2,
    "ffx_fsr3updater_x64.dll": Upscaler.FSR2,
}
_FG_FILES = ["sl.dlss_g.dll", "nvngx_dlssg.dll", "sl.dlssg.dll"]


def _pe_header(exe: Path) -> tuple[int, list[str]]:
    """Devolve (bits, imports) lendo o PE com struct (sem dependências).

    bits: 32 ou 64 (0 se não for PE válido)
    imports: nomes de DLLs importadas (lowercase), limitado a 256.
    """
    try:
        # imports podem ficar longe do início em executáveis grandes (RDR2: 89MB)
        with exe.open("rb") as fh:
            data = fh.read()
    except OSError:
        return 0, []
    if len(data) < 0x400 or data[:2] != b"MZ":
        return 0, []
    try:
        e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
        if data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
            return 0, []
        coff = e_lfanew + 4
        machine, _, _, _, _, opt_size, _ = struct.unpack_from("<HHIIIHH", data, coff)
        bits = 64 if machine == 0x8664 else 32 if machine == 0x14C else 0
        opt = coff + 20
        magic = struct.unpack_from("<H", data, opt)[0]
        # data directories offset: PE32+ = 112, PE32 = 96
        dd_off = opt + (112 if magic == 0x20B else 96)
        import_rva, import_size = struct.unpack_from("<II", data, dd_off + 8)
        # section table p/ converter RVA→file offset
        sec_off = opt + opt_size
        num_sec = struct.unpack_from("<H", data, coff + 2)[0]
        sections = []
        for i in range(num_sec):
            s = sec_off + i * 40
            vsize, vaddr, rsize, raddr = struct.unpack_from("<IIII", data, s + 8)
            sections.append((vaddr, vsize, raddr, rsize))
        def rva_to_off(rva: int) -> int:
            for vaddr, vsize, raddr, rsize in sections:
                if vaddr <= rva < vaddr + max(vsize, rsize):
                    return raddr + (rva - vaddr)
            return 0
        imports: list[str] = []
        off = rva_to_off(import_rva)
        if off:
            while off + 20 <= len(data) and len(imports) < 256:
                ilt_rva, _, _, name_rva, _ = struct.unpack_from("<IIIII", data, off)
                if name_rva == 0:
                    break
                n_off = rva_to_off(name_rva)
                if n_off:
                    end = data.find(b"\0", n_off)
                    name = data[n_off:end].decode("ascii", "ignore").lower()
                    imports.append(name)
                off += 20
        return bits, imports
    except (struct.error, IndexError):
        return 0, []


def classify(game: Game) -> Game:
    exe = Path(game.exe_path)
    folder = exe.parent
    game.pe_bits, game.imports = _pe_header(exe)

    # API gráfica: imports do PE primeiro, depois DLLs soltas na pasta.
    # Jogos multi-API (ex.: RDR2 importa d3d9 + fsr2_dx12 + fsr2_vk + nvlowlatencyvk)
    # ficam com a MELHOR API: DX12 > DX11 > Vulkan > resto.
    rank = {API.DX12: 5, API.DX11: 4, API.VULKAN: 3, API.DX10: 2, API.DX9: 1,
            API.OPENGL: 1, API.UNKNOWN: 0}
    best = API.UNKNOWN
    for imp in game.imports:
        cand = _API_DLLS.get(imp)
        if cand and rank[cand] > rank[best]:
            best = cand
    if best == API.UNKNOWN:
        for f in folder.glob("*.dll"):
            cand = _API_DLLS.get(f.name.lower())
            if cand and rank[cand] > rank[best]:
                best = cand
    # pistas fortes de DX12 mesmo sem import direto (carregamento dinâmico):
    # fsr2_dx12 / nvngx / streamline na pasta indicam runtime DX12
    imp_text = " ".join(game.imports)
    if best.value in ("DX9", "DX10", "UNKNOWN"):
        if "fsr2_api_dx12" in imp_text or "nvngx" in imp_text or "sl.dlss" in imp_text:
            best = API.DX12
    game.api = best.value

    # upscaler presente — prioriza DLSS2 (habilita a ponte MFG NVIDIA);
    # jogos podem ter vários (RDR2 tem DLSS2 + FSR2)
    prio = {Upscaler.DLSS2: 3, Upscaler.XESS: 2, Upscaler.FSR2: 1, Upscaler.NONE: 0}
    up = Upscaler.NONE
    for f in folder.rglob("*.dll"):
        cand = _UPSCALER_FILES.get(f.name.lower())
        if cand and prio[cand] > prio[up]:
            up = cand
    game.upscaler = up.value

    # Frame generation NATIVA (o jogo já sabe fazer FG sozinho).
    #
    # CUIDADO: não contar os arquivos que NÓS instalamos. Depois que o fork é
    # instalado, existe `OptiScaler/streamline/sl.dlss_g.dll` na pasta — e um
    # rglob achando qualquer sl.dlss_g.dll declarava o jogo como "tem FG
    # nativa". Isso se autoalimenta: instalar o fork fazia o classificador
    # concluir que FG era nativa, e o próximo decide() parava de reinstalar.
    def _is_ours(p: Path) -> bool:
        parts = {x.lower() for x in p.parts}
        return "optiscaler" in parts or "licenses_dlssnr" in parts

    game.fg_native = any(
        f.exists() and not _is_ours(f) for f in (folder / n for n in _FG_FILES)
    ) or any(
        f.exists() and not _is_ours(f) for f in folder.rglob("sl.dlss_g.dll")
    )

    # anti-cheat: arquivos/pastas na árvore do jogo
    ac: list[str] = []
    folder_lower = str(folder).lower()
    for f in folder.rglob("*"):
        n = f.name.lower()
        if any(h in n for h in _AC_HINTS):
            ac.append(f.name)
            if len(ac) >= 3:
                break
    game.ac_names = ac
    game.anticheat = bool(ac)
    return game
