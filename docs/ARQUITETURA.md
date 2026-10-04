# 🏗️ TurboPlay — Arquitetura

## Pipeline (MVP)

```
[1. DISCOVERY]  →  [2. CLASSIFY]  →  [3. PROFILE]  →  [4. APPLY]  →  [5. VERIFY]
   scanner.py        classifier.py      profiles.py      applier.py      applier.py
```

### 1. Discovery — onde acham jogos

| Fonte | Como |
|---|---|
| Steam | `%ProgramFiles(x86)%\Steam\steamapps\libraryfolders.vdf` → `common/` |
| SAMBOX/RetroBat | `<root>/sistema/roms/**/*.bat` → parse do `start` p/ achar exe real de jogo PC nativo |
| Pastas custom | recursivo, .exe com metadata de jogo (heurística: tamanho, ícone, OriginalFilename) |

**Insight do SAMBOX:** os `.bat` são atalhos do frontend. Um `.bat` que chama
`Launcher.exe`/`RDR2.exe` = jogo PC nativo (classificável). Um `.bat` que chama
`retrobat.exe`/emulador = conteúdo emulado (rota diferente: perfil de emulador).

### 2. Classify — o que é aquele jogo

Lê o PE do executável (struct parsing, stdlib):
- **Imports** → d3d12.dll? dxgi? d3d11? d3d9? vulkan-1?
- **Arquivos vizinhos** → `nvngx_dlss.dll` (DLSS2), `sl.dlss_g.dll` (FG nativa
  Streamline), `libxess.dll` (XeSS), `ffx_fsr2_*.dll` / `amd_fidelityfx_*` (FSR),
  `nvngx_dlssg.dll` (DLSS-G direto)
- **Anti-cheat** → subpastas `BattlEye/`, `EasyAntiCheat/`, dlls `BEService`,
  `easyanticheat`, `vmp-64.dll` (VMProtect), `Denuvo`
- **Engine** (fase 2) → Unreal (`*.pak`, `Engine/`), RE Engine (rechunk), etc.

Saída: `GameClass` = {
  api: DX12|DX11|DX9|VULKAN, upscaler: DLSS2|XESS|FSR2|NONE,
  fg_native: bool, anticheat: bool, exe_path, folder
}

### 3. Profile — qual stack aplicar (matriz GPU × jogo)

Regras (ordem = prioridade):

```
SE anticheat                          → NOOP (nunca mexer)
SE !api==DX12                         → rota alternativa (Lossless/XeSS-DP4a/emulador)
SE gpu==RTX50                         → MFG nativo já existe; só DLSS Swapper se faltar DLL
SE gpu==RTX20/30/40 E fg_native       → [SM86 proxy]  (destrava MFG no menu do jogo)
SE gpu==RTX20/30/40 E !fg_native E upscaler==DLSS2
                                      → [OptiScaler + DLSS Enabler + SM86]  (caso RDR2)
SE gpu==RTX20/30/40 E upscaler==NONE  → [OptiScaler OptiFG] ou rota ReShade/RenoDX
SE gpu==AMD/Intel                     → [OptiScaler XeFG/FSR-FG] ou XeSS-DP4a
```

Perfis específicos por jogo (JSON) corrigem exceções — ex. RDR2:
`winmm.dll`, `remove fakenvapi`, `DX12 required`, `HUDFix se flicker`.

### 4. Apply — instalação invisível e reversível

- Download dos releases oficiais GitHub (OptiScaler, DLSS Enabler, dlssg_for_sm86)
- Cache local com hash SHA-256 (não baixa duas vezes, não baixa versão alterada)
- Backup pré-instalação → `%LOCALAPPDATA%\TurboPlay\backups\<game-id>\`
- Instalação: copia arquivos, renomeia DLL conforme perfil, escreve INI do perfil
- Cria desinstalador + registro de instalação em `installed.json`

### 5. Verify — confirmar que funcionou (sem o usuário abrir nada)

- Primeiro launch pós-instalação: lê `dlssg_sm86\logs\backend_*.jsonl`
  (procura `install` com `route active=true`) e `OptiScaler.log`
- Se falhou → rollback automático + marca jogo como "incompatível" (sem retry infinito)
- Se ok → marca como ativo; futuro: telemetria local de FPS (CapFrameX/RTSS, opcional)

## Futuro (pós-MVP)

- **Serviço residente**: watcher do filesystem/Steam → novo jogo instalado =
  pipeline roda sozinho na primeira execução
- **Tray app**: ícone discreto; notificação única "TurboPlay otimizou 3 jogos"
- **UI oculta**: painel só pra quem quiser ver (senha opcional); jogador comum nunca entra
- **Base de perfis comunitária**: JSON versionado em repo público, curadoria via PR
