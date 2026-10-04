# 🚀 TurboPlay v1.5 — Emulados estáveis + melhorias automáticas ✅

## v1.5 (21/09/2026) — NES/SNES abrindo + perfis de qualidade por emulador

**Causa raiz dos NES/SNES que não abriam:** o retroarch.cfg do SAMBOX usa
caminhos relativos (`:\cores`) que só resolvem com o cwd correto. Teste manual
confirmou: RetroArch + Nestopia abriu "1942 (NES)" quando o cwd é a pasta do
retroarch. Correção: rota RetroArch-direto pra sistemas 2D (psx?? não — 2D:
nes/snes/gb/gba/megadrive/n64/dreamcast/arcade/neogeo/pcengine/saturn...)
com cwd = pasta do retroarch; dedicados (Duckstation etc.) continuam com
cwd = pasta deles.

**Melhorias automáticas (`emuperf.py`)** — as melhorias que o SAMBOX tem
escondidas, agora ligadas por padrão, com backup:
- PS1 (Duckstation): Vulkan, ResolutionScale=8 (4K), PGXP (geometria 3D
  corrigida), culling fix, xBR filtering, dithering escalado → APLICADO
- PS2 (PCSX2): upscale 6x, filtering, anisotropy 8
- GC/Wii (Dolphin): InternalResolution 4K, anisotropy
- aplicação JIT no fluxo JOGAR (antes de abrir) + backup em
  %LOCALAPPDATA%\TurboPlay\emulator_backups- idempotente e reversível (rollback restaura o INI original)

**Validado:** PS1 perfil aplicado (8 ajustes) + backup criado; exe v1.5
compilado e instalado (11 MB).

---

# 🚀 TurboPlay v1.4 — Lupa de busca + emuladores corrigidos ✅

## v1.4 (21/09/2026) — marcha por marca + lupa; jogos emulados abrindo

**Bug de emuladores corrigido (`emulaunch.py`):**
- causa: nomes de exe diferentes (Duckstation = duckstation-qt-x64-ReleaseLTCG.exe)
  e emuladores ausentes (PPSSPP/mupen64/flycast/melonds não têm exe próprio)
- resolução dinâmica: template → fallbacks → maior exe da pasta
- fallback RetroArch + cores libretro CONFIRMADOS na pasta (nestopia, snes9x,
  gambatte, mgba, genesis_plus_gx, mednafen_psx_hw, mupen64plus_next, flycast,
  fbneo, ppsspp, melonds, dolphin, citra, stella...)
- RetroArch genérico como último recurso (resolve core pela extensão)

**Lupa de busca (`searchlib.py`) — ideia do Saimon:**
- busca em tempo real enquanto digita, com cascata:
  1. marca/console ("ps1", "super nintendo", "mega drive") → lista só do console
  2. gênero ("futebol" → 17 jogos, "luta" → 79, "corrida", "rpg"...)
  3. nome ("sonic" → 7 jogos) exato e parcial
- sinônimos PT-BR (fliperama=arcade, play 2=ps2, nitendo 64=n64...)
- lista de resultados também agrupada por console

**Validado:** busca futebol=17, luta=79, sonic=7, ps1=1 (RE1);
Duckstation exe resolvido; biblioteca completa = 1.827 jogos de console;
exe v1.4 compilado, instalado e testado (janela abre).

---

# 🚀 TurboPlay v1.3 — Reconhecimento automático total ✅

## v1.3 (21/09/2026) — "ele vai reconhecer qualquer jogo novo?" → SIM

- `watcher.py`: vigia Steam common + roms do SAMBOX em tempo real (thread
  daemon, snapshot de mtimes, debounce); detectou mudança →
  `auto_optimize_new_games()` otimiza SÓ os novos (estado incremental) e
  notifica via toast "Novo jogo otimizado: X"
- GUI: watcher integrado (jogando com o TurboPlay aberto, jogo novo aparece
  e já vem otimizado na lista) + botão "Auto no boot: LIGADO/desligado"
- `autostart.py`: HKCU Run key (sem UAC) → `TurboPlay.exe watch --silent`
  no logon do Windows; otimiza novos jogos em segundo plano pra sempre
- Atalho da área de trabalho recriado (OneDrive tinha removido)
- Validado: autostart LIGADO no registro; exe v1.3 instalado e testado

---

# 🚀 TurboPlay v1.1 — Launcher de Jogos ✅

## v1.1 (21/09/2026) — a ideia do Saimon: jogar direto pelo TurboPlay

**Fluxo console:** abre o TurboPlay → lista de jogos com ✅ → clica ▶ JOGAR
(duplo clique também funciona) → pré-otimização JIT (cache) → jogo abre →
quando fecha, o TurboPlay lê os logs e confirma via toast.

- `launcher.py`: pre_launch → launch → post_launch_watch
- `gui.py` v2: biblioteca com marcação ✅, botão ▶ JOGAR, duplo-clique, log
- Steam via `steam://rungameid/<appid>` (respeita DRM/overlay); SAMBOX via .bat
- `pipeline.get_library()` alimenta a GUI; `optimize_one()` faz JIT por jogo
- exe v2 compilado e instalado em `%LOCALAPPDATA%\TurboPlay\TurboPlay.exe`

---

## v1.0 — base instalada

Data: 21/09/2026 · Máquina: Saimon (RTX 3060, driver 616.56, Win11)

## O que foi entregue

- **Executável standalone** (PyInstaller onefile, 7 MB, sem Python exigido):
  `C:\Users\saimi\AppData\Local\TurboPlay\TurboPlay.exe`
- **Atalho na área de trabalho**: `Desktop\TurboPlay.lnk`
- **GUI amigável** (tkinter): janela com status, botão "🔄 Otimizar agora",
  botão "↩️ Reverter tudo", log legível
- **Pipeline completo**: scan → classificação → decisão → aplicação → verificação
- **Fonte do projeto** no vault: `Projetos/TurboPlay/`

## Capacidades v1.0

| Camada | Estado |
|---|---|
| Scanner Steam (libraryfolders.vdf) | ✅ |
| Scanner SAMBOX/RetroBat (parse .bat com `cd`+`start`, resolve relativo, escolhe exe principal) | ✅ validado (achou RDR2 em roms/ps5) |
| Classificador PE (API por imports + ranking, upscalers, FG nativa, anti-cheat) | ✅ validado (RDR2 = DX12/DLSS2) |
| Motor de perfis (GPU NVIDIA série 20/30/40/50, AMD, Intel; overrides por jogo) | ✅ |
| Applier (backup → instalar → INI overrides → desinstalador) | ✅ |
| Camada OptiScaler (cache oficial 0.9.4) | ✅ aplicada no RDR2 |
| Camada SM86 (dlssg_for_sm86 0.3.5) | ✅ aplicada no RDR2 |
| Camada DLSS Enabler | ⚠️ pulada (pacote local ausente; Nexus requer login) |
| Rollback (`rollback --all` / botão GUI) | ✅ |
| Modo residente (`watch`, intervalo 30 min) + toast | ✅ |
| Estado | `%LOCALAPPDATA%\TurboPlay\installed.json` + `backups\` |

## Uso

- **Janela**: duplo clique no atalho → "Otimizar agora"
- **CLI**: `TurboPlay.exe scan | apply | rollback --all | watch`

## Próximos (v1.1)

1. Baixar DLSS Enabler (Nexus, login manual) → soltar em
   `_downloads\dlss-enabler\` → camada ponte completa no RDR2
2. Testar RDR2 in-game (menu Insert, FSR-FG; depois MFG via Enabler+SM86)
3. Autostart opcional (chave Run) com `watch --once` no logon
4. Ícone próprio + assinatura de código

---

## v1.2 (21/09/2026) — Consoles: front-end universal

**A extensão pedida pelo Saimon:** emuladores também jogáveis direto pelo
TurboPlay, com classificação por videogame e melhorias por sistema.

- `systems.py`: catálogo de 56+ sistemas (gen 2→9: Atari→PS5/Switch/Xbox360)
  com emulador padrão SAMBOX e melhorias recomendadas por console
  (ex.: PS1 → PGXP+4K no Duckstation; Switch → fork ryubing-dlss5 com DLSS5+FG)
- `consolelib.py`: varre roms/ do SAMBOX, lê gamelist.xml (nomes/capas),
  resolve aliases locais (ps5→PS5, megadrivebr→Mega Drive...), detecta
  .bat = PC nativo disfarçado
- `emulaunch.py`: CLI específica por emulador (Duckstation -nogui, Dolphin -b -e,
  Cemu -g -f...) + fallback RetroArch com cores libretro por sistema
- GUI v3: abas "🖥️ Meus Jogos (PC)" e "🕹️ Consoles"; consoles agrupados por
  geração com emulador; painel mostra as melhorias disponíveis do sistema
- Validado na máquina: 56 sistemas, RE1 = PS1/duckstation, RDR2 = PC nativo
- exe v1.2 compilado e instalado

**Melhorias de emulador (roadmap v1.3):** aplicar perfis automaticamente nos
emuladores (Duckstation.ini: internal 4x+PGXP; PCSX2: 4K+widescreen; Dolphin:
4K; RetroArch: shaders CRT) — hoje o TurboPlay mostra as melhorias; v1.3 aplica.
