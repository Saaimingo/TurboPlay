# 🎮 TurboPlay — performance invisível

> *"O jogador só aperta botão e joga. O que acontece por trás não é problema dele."*

## O produto

Software residente que analisa **cada jogo** instalado na máquina e aplica
**automaticamente, sem que o usuário saiba**, a melhor stack de melhoria
gráfica/performance disponível para aquele jogo na **placa que ele tem**.

- Jogo só aceita OptiScaler? → aplica OptiScaler, configurado, sem perguntar.
- Jogo aceita MFG+DLSS5? → aplica a stack completa (fork OptiScaler-DLSSNR + SM86).
- Jogo com FG nativa (ex.: RDR2)? → a stack dele continua com DLSSG por via Streamline.
- Jogo DX9/DX11/emulado? → aplica o que der (perfil de emulador, XeSS/FSR disponível).
- Jogo com anti-cheat? → **não mexe em nada** (segurança absoluta).
- Placa AMD/Intel? → mesma decisão inteligente, com as stacks corretas pra cada vendor.

O público: **90% das pessoas não são programadores** — vieram do video game,
só apertam botão. O TurboPlay é invisível: instala uma vez, roda sozinho,
e o jogador só percebe que "o PC tá rodando tudo liso e bonito".

## Princípios inegociáveis

1. **Zero interação** — nenhuma tela técnica, nenhum INI, nenhum menu exposto.
2. **Reversível sempre** — toda instalação tem rollback automático e seguro.
3. **Segurança acima de FPS** — anti-cheat detectado = jogo intocável.
4. **Fontes oficiais apenas** — OptiScaler e dlssg_for_sm86 baixados dos releases
   oficiais, com hash validado. O repack comunitário é aceito só quando o titular o
   validou manualmente.
5. **Vendor-agnostic** — NVIDIA 20/30/40/50, AMD, Intel: cada uma recebe o que lhe serve.

## Stack técnica

- Python 3 (o core usa stdlib; Pillow é dependência declarada porque a GUI importa
  o módulo de capas locais, cujo uso visual é opcional).
- `pyproject.toml`: metadata + entry point `turboplay = "src.main:main"`.
- Scanner: Steam (`libraryfolders.vdf`) + **SAMBOX/RetroBat** (sabe ler os `.bat`
  de atalho que apontam pra jogos PC nativos — ninguém mais faz isso) + Xbox/Store +
  Epic + GOG + pastas custom.
- Classificador: lê imports do PE (DX12/DX11/DX9), detecta `nvngx_dlss.dll`,
  `libxess`, `ffx_*`, FG nativa (Streamline `sl.dlss_g.dll`), anti-cheat
  (`BattlEye`, `EasyAntiCheat`, `vmp`, etc.).
- Motor de perfis (`src/profiles.py`): GPU + classificação → stack de camadas.
- Aplicador (`src/applier.py`): instala + valida logs (`OptiScaler.log`,
  `dlssg_sm86/logs`) + rollback.
- Sistema de mods (`src/mods.py`): instala zip/rar escolhido pelo jogador, detecta
  estrutura (desembrulho de pasta única, regras por tipo — `reframework/`, `.dll` na
  raiz, etc.), registra cada arquivo num manifest `turboinstall.mods.json` por jogo
  e permite remover depois. A GUI tem diálogo "Instalar mod…" (jogo → arquivo → ok).

## Onde o OptiScaler.ini fica (exemplo RE3)

Cada jogo otimizado leva o seu próprio `OptiScaler.ini` **na raiz da pasta do jogo**.
Exemplo: `D:\SteamLibrary\steamapps\common\RE3\OptiScaler.ini`.

Isso é importante pra não confundir com o OptiScaler.ini global de debug que você
pode ter em outra pasta (ex.: `D:\Games\SAMBOX-Vfull\sistema\roms\ps5\sistema\roms\
ps4eps5installars\Red Dead Redemption 2\OptiScaler.ini`).

Para RE3, o perfil força agora (OptiFG, jogo sem FG nativa):
- `[FrameGen] FGOutput = fsrfg`
- `[FrameGen] FGNvngxReplacement = FFX`
- `[OptiFG] HUDFix = true`

## Estrutura

```
TurboPlay/
├── README.md
├── pyproject.toml          # metadata + entry point
├── TurboPlay.spec          # (build de distribuição, se usado)
├── docs/
│   ├── ARQUITETURA.md
│   └── DECISOES.md
├── mods/                   # biblioteca de mods por jogo (zip/rar prontos)
├── src/
│   ├── main.py             # entrypoint (GUI ou CLI)
│   ├── turboplay.py        # CLI de orquestração
│   ├── scanner.py          # descobre jogos
│   ├── classifier.py       # analisa cada jogo
│   ├── profiles.py         # motor de perfis
│   ├── applier.py          # instala + rollback + verificação
│   ├── mods.py             # sistema de instalação/remoção de mods
│   ├── gui.py              # launcher GUI (tkinter)
│   ├── launcher.py         # pré-launch JIT + pós-lançamento
│   ├── providers.py        # Steam, Xbox, Epic, GOG, custom, SAMBOX
│   ├── watcher.py          # vigia de biblioteca sem perda de evento
│   ├── enabler.py
│   ├── emulaunch.py
│   ├── emuperf.py
│   ├── consolelib.py
│   ├── searchlib.py
│   ├── systems.py
│   ├── resident.py
│   ├── scanconsolelib.py
│   ├── autostart.py
│   ├── notify.py
│   └── __init__.py
└── tests/                  # suíte de testes
```

## Estado

- [x] Investigação das stacks (OptiScaler, dlssg_for_sm86, repack comunitário)
- [x] MVP: scanner + classificador + applier
- [x] Descoberta multi-provedor: Steam, Xbox/Store, Epic, GOG, SAMBOX, pastas custom
- [x] Stack **DLSS 5 + MFG** no motor de perfis (fork OptiScaler-DLSSNR + SM86)
- [x] Watcher sem perda de evento (mtime por subpasta) + autostart via pasta Inicializar
- [x] GUI de launcher (cards, busca, filtros, instalação de mods)
- [x] Sistema de mods: instala/remoção com manifest por jogo
- [x] Rota OptiFG para RE Engine pré-DLSS3 (RE3/RE2/RE7/RE8/DMC5): `fg_native=True`
  no classifier está correto sobre os DLLs embacados, mas o jogo nunca chama
  `slDLSSGSetState` → rota `fsrfg + FFX + HUDFix=true` aplicada automaticamente
- [ ] Testes: suíte própria (`tests/`)
- [ ] Build de distribuição: `TurboPlay.exe` via PyInstaller/spec

## Erros / limites conhecidos

- **Game Pass / Microsoft Store não é otimizável.** São pacotes MSIX assinados em
  `WindowsApps`; injetar DLL quebra a assinatura e o jogo deixa de abrir. O TurboPlay
  detecta e explica em vez de prometer.
- **Só DX12** entra na rota de injeção hoje. DX11/DX9/Vulkan e emulados ficam
  para a fase seguinte.
- **Pasta sem escrita** (instalação em `C:\Program Files`, falta de admin) → o
  jogo é detectado com o motivo e fica intocado.
- **OptiFG é experimental** (conforme a própria wiki do OptiScaler). Quando funciona,
  entrega FG de verdade em jogos sem suporte nativo; pode haver ghosting de HUD ou
  instabilidade ao alternar FG. Se o HUD ficar duplicado, ajuste o HUDFix Limit no
  menu do Insert; se crashar ao ligar FG, reportar pra ajustar a rota.
- **RE Engine antigo + REFramework**: o REFramework genérico do repack congela RE3
  em tela preta (swapchain). Esse jogo precisa do `dinput8.dll` específico do Nexus,
  não automático pelo TurboPlay. O overlay do OptiScaler (`dxgi.dll`) funciona
  independente disso.

## Uso

```bash
# CLI (se você tiver o script/main.py rodando como module ou executável)
turboplay scan              # lista jogos/decisões; pode testar escrita e extrair fork RAR em cache local
turboplay scan --json       # saida machine-readable
turboplay apply --dry-run   # não aplica camadas nem salva estado; a descoberta ainda faz probe transitório de permissão nas pastas detectadas
turboplay apply             # aplica de verdade (exige integridade da stack)
turboplay rollback --all    # reverte tudo
turboplay watch --dry-run   # sem instalar/salvar estado; verifica stack e pode extrair fork RAR; descoberta testa escrita
turboplay autostart on      # atalho na pasta Inicializar (sem registro)

# GUI
turboplay                 # abre o launcher
```

## Repo

- `https://github.com/Saaimingo/TurboPlay` — público, sem fork.
- Branch padrão: `v2.6-fg-re3-optifg` (feat OptiFG RE Engine + sistema de mods).
- Relatório de auditoria local (10/10/2026): [`docs/RELATORIO-AUDITORIA-2026-10-10.md`](docs/RELATORIO-AUDITORIA-2026-10-10.md).
