# 🎮 TurboPlay — performance invisível

> *"O jogador só aperta botão e joga. O que acontece por trás não é problema dele."*

## O produto

Software residente que analisa **cada jogo** instalado na máquina e aplica
**automaticamente, sem que o usuário saiba**, a melhor stack de melhoria
gráfica/performance disponível para aquele jogo na **placa que ele tem**.

- Jogo só aceita OptiScaler? → aplica OptiScaler, configurado, sem perguntar.
- Jogo aceita MFG+DLSS5? → aplica a stack completa (OptiScaler + DLSS Enabler + SM86).
- Jogo DX9/DX11/emulado? → aplica o que der (Lossless Scaling, perfil de emulador, XeSS-DP4a).
- Jogo com anti-cheat? → **não mexe em nada** (segurança absoluta).
- Placa AMD/Intel? → mesma decisão inteligente, com as stacks corretas pra cada vendor.

O público: **90% das pessoas não são programadores** — vieram do video game,
só apertam botão. O TurboPlay é invisível: instala uma vez, roda sozinho,
e o jogador só percebe que "o PC tá rodando tudo liso e bonito".

## Princípios inegociáveis

1. **Zero interação** — nenhuma tela técnica, nenhum INI, nenhum menu exposto.
2. **Reversível sempre** — toda instalação tem rollback automático e seguro.
3. **Segurança acima de FPS** — anti-cheat detectado = jogo intocável.
4. **Fontes oficiais apenas** — OptiScaler, DLSS Enabler, dlssg_for_sm86 baixados
   dos releases oficiais no GitHub, com hash validado.
5. **Vendor-agnostic** — NVIDIA 20/30/40/50, AMD, Intel: cada uma recebe o que lhe serve.

## Stack técnica (MVP)

- Python 3 (stdlib only no core — sem dependências pra quem instala)
- Scanner: Steam (libraryfolders.vdf) + pastas custom + **SAMBOX/RetroBat**
  (sabe ler os `.bat` de atalho que apontam pra jogos PC nativos — ninguém faz isso)
- Classificador: lê imports do PE (DX12/DX11/DX9), detecta `nvngx_dlss.dll`,
  `libxess`, `ffx_*`, FG nativa (Streamline `sl.dlss_g.dll`), anti-cheat
  (`BattlEye`, `EasyAntiCheat`, `vmp`, etc.)
- Motor de perfis: YAML/JSON por jogo + regras genéricas por classe
- Aplicador: instala + valida logs (`optiscaler.log`, `dlssg_sm86\logs`) + rollback

## Estrutura

```
TurboPlay/
├── README.md            ← você está aqui
├── docs/
│   ├── ARQUITETURA.md   ← como o sistema funciona por dentro
│   └── DECISOES.md      ← registro de decisões de produto/tecnologia
├── src/
│   ├── scanner.py       ← descobre jogos instalados
│   ├── classifier.py    ← analisa cada jogo (API, upscaler, anti-cheat)
│   ├── profiles.py      ← motor de perfis (GPU + jogo → stack)
│   ├── applier.py       ← instala com backup/rollback
│   └── turboplay.py     ← CLI de orquestração (futuro: serviço residente)
└── tests/               ← testes com a máquina real do Saimon como caso de uso
```

## Estado

- [x] Investigação das stacks (OptiScaler, DLSS Enabler, dlssg_for_sm86, DLSS5 Manager)
- [x] MVP: scanner + classificador + applier
- [x] Descoberta multi-provedor: Steam, Xbox/Store, Epic, GOG, SAMBOX, pastas custom
- [x] Stack **DLSS 5 + MFG** no motor de perfis (fork v0.8.7 + Streamline, hash pinado)
- [x] Watcher sem perda de evento (mtime por subpasta) + autostart via pasta Inicializar
- [x] Suíte de testes (`python tests/test_pipeline.py`) — 24/24
- [x] Validação real: máquina do Saimon (RTX 3060, SAMBOX, Steam vazia)
- [ ] GUI de bandeja do sistema (ícone discreto, status "tudo pronto")

## Limites conhecidos (dizemos na cara do jogador)

- **Game Pass / Microsoft Store não é otimizável.** São pacotes MSIX assinados em
  `WindowsApps`; injetar DLL quebra a assinatura e o jogo deixa de abrir. O
  TurboPlay detecta e explica em vez de prometer.
- **Só DX12** entra na rota de injeção hoje. DX11/DX9/Vulkan e emulados ficam
  para a fase seguinte.
- **Pasta sem escrita** (instalação em `C:\Program Files`, falta de admin) → o
  jogo é detectado com o motivo e fica intocado.

## Uso

```bash
TurboPlay.exe scan              # lista o que ele enxergou, por provedor, e o que faria
TurboPlay.exe scan --json       # saida machine-readable
TurboPlay.exe apply --dry-run   # mostra o que faria, sem escrever em nenhum jogo
TurboPlay.exe apply             # aplica de verdade (exige integridade da stack)
TurboPlay.exe rollback --all    # reverte tudo
TurboPlay.exe watch --dry-run   # vigia e avisa, sem instalar
TurboPlay.exe autostart on      # atalho na pasta Inicializar (sem registro)
```
