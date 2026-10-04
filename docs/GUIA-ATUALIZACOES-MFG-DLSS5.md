# 🔄 Guia de Vigília — Atualizações MFG + DLSS 5 (RTX série 30)

> **Pra quê:** os mods que destravam MFG/DLSS 5 na série 30 são lançados por modders
> **quase diariamente** — e cada versão nova costuma consertar um crash que atinge
> exatamente a gente (RTX 30/20 é o alvo experimental). Este doc diz **onde olhar**,
> **com que frequência** e **como atualizar sem quebrar**.

**Última verificação ao vivo: 21/09/2026 (noite).**

---

## 1. Onde olhar (em ordem de importância pra série 30)

| # | Fonte | O que fornece | Cadência observada | Quando atualizar |
|---|---|---|---|---|
| 1 | **`sdli1995/dlssg_for_sm86` → Releases** — github.com/sdli1995/dlssg_for_sm86/releases | O **proxy que destrava o MFG** da NVIDIA em RTX 20/30 (reporta RTX 50 ao jogo, kernels recompilados pra Ampere). É o componente mais crítico | 🔥 Altíssima: 6 releases em 5 dias (14→19/09) | **Toda fix de crash/corrupção** — afeta a gente direto |
| 2 | **`NODIX-TECH/DLSS-5-MANAGER` → Releases** — github.com/NODIX-TECH/DLSS-5-MANAGER/releases | Orquestrador one-click (o do vídeo). 1.2.8 (vídeo) → **1.3.2 lançada 21/09**: Live Flow roda DLSS 5 em **qualquer** app/jogo (modo borderless), MFG até 6x beta, XeSS MFG | 🔥 Alta | Quando sair feature que a gente quer (Live Flow, suporte novo) |
| 3 | **`wilsjo2/OptiScaler-DLSSNR-PreSR-Multipass` → Releases** — github.com/wilsjo2/... | Fork OptiScaler com **DLSS 5 Neural Render** (o "DLSS 5 de verdade"). Nosso pacote é **v0.7.6**; já existe **v0.8.7 pre-release (21/09)** com fixes grandes de memória/shutdown | Média-alta (pre-releases) | Só com release note lida — é experimental; o RDR2 é citado nas issues dele (PR #70) |
| 4 | **`optiscaler/OptiScaler` → Releases** — github.com/optiscaler/OptiScaler/releases | OptiScaler base (upscaler universal + FSR3-FG). Nossa base: 0.9.4 | Média | Updates de estabilidade/qualidade |
| 5 | **Nexus — DLSS Enabler** (artur07305) — nexusmods.com/site/mods/757 | A **ponte de FG** pra jogos sem FG nativa (RDR2). **Sem GitHub — só no Nexus** (exige login) | Média | Checar aba "Updates" manualmente de vez em quando |
| 6 | Telegram do canal Tech Games | Repack BR de tudo (conveniência) | Segue os oficiais | **Nunca como fonte primária** — chega atrasado; preferir o repo oficial |

### ⚠️ O caso especial do DLSS Enabler (por que não veio em nenhum pacote "completo")

**Arquivo correto no Nexus:** `DLSS Enabler 4.9.0 STABLE` (7.7MB, Main files,
aba *Files* → *Manual download* → baixar lento grátis serve).
URL: https://www.nexusmods.com/site/mods/757?tab=files

**Por que os pacotes do Telegram/vídeo não o incluem (e mesmo assim se dizem
"completos"):** eles são completos **para o caso comum** — jogos que já têm FG
nativa (RE Requiem, Cyberpunk...) ou a rota OptiScaler/FSR3. O Enabler só é
necessário no caso especial: **jogo DX12 SEM FG nativa (RDR2, jogos 2021–2023)**.
E como o autor distribui **exclusivamente pelo Nexus** (não há GitHub), os
repacks não o re-distribuem — por isso é a única peça que precisa de login
manual. Conta grátis no nexusmods.com resolve.

---

## 2. Snapshot de versões — 21/09/2026

| Componente | Temos instalado | Último oficial (21/09) | Situação |
|---|---|---|---|
| Proxy SM86 (`version.dll`) | **0.3.5** | 0.3.5 (19/09) — **atenção: releases do GitHub NÃO têm binários** (só fonte) | ✅ atualizado. Fix da 0.3.5: frames corrompidos/crash quando o jogo **recria a FG** (trocar resolução, mudar qualidade, ligar/desligar FG no menu) — cenário que o TurboPlay mexe, relevante |
| DLSS 5 Manager | (não usamos — pipeline próprio do TurboPlay) | **1.3.2** (21/09) | Referência; Live Flow pode valer teste futuro |
| OptiScaler base | 0.9.4 | conferir repo | Usar no RDR2 |
| Fork DLSSNR | **0.7.6** (extraído em `D:\Games\MFG-NVIDIA-DLSS5\_downloads\optiscaler_dlssnr_076\`) | **0.8.7 pre** (21/09) | ⚠️ A 0.8.x corrigiu bugs sérios de NR — mas são *pre-releases*. Esperar estabilizar antes de pôr no RDR2; as runtimes NVIDIA do nosso pacote (`nvngx_dlssg/dlssnr/dlssd.dll`) continuam válidas (a 0.8.7 não vem com elas) |
| DLSS Enabler | ✅ **4.9.0 instalado no RDR2** (como dxgi.dll) | 4.9.0 (31/08) | Zip já em `_downloads\dlss-enabler\`; TurboPlay instala sozinho em outros jogos |

---

## 3. Regras pra série 30 (duramente aprendidas pela comunidade)

1. **Ler a release note ANTES de atualizar.** Cada versão conserta algo e às vezes
   introduz outro (a 0.3.3 causou driver reset na RTX 30; a 0.3.4 consertou —
   causa: NVIDIA App fazendo override de DLSS junto com o proxy).
2. **Nunca misturar versões** de fontes diferentes na mesma pasta de jogo
   (mesma dor do comentário do KelKoNeTo1 no vídeo: MFG de um pacote + DLSS5 de
   outro = conflito de arquivos).
3. **NVIDIA App**: desligar o override de DLSS enquanto usar o proxy SM86.
4. **Backup antes de trocar** (`version.dll` + INI → `.tp-bak`). O TurboPlay faz
   sozinho; na mão, copiar antes.
5. **Validar depois de atualizar:** abrir o jogo → ligar FG 2x → trocar resolução →
   voltar → conferir que não deu artefato/crash (é o cenário do fix 0.3.5) e ler os
   logs (`dlssg_sm86\logs`, `optiscaler.log` na pasta do jogo).
6. **`Optimized`**: escala 0–3 (padrão **1 = imagem bit-a-bit idêntica** à oficial;
   2/3 = mais rápido com perda). Deu artefato? Volta pra 1.
7. **4X é o padrão seguro na 3060.** 6X exige build 310.9 do proxy +
   `MaxGeneratedFrames=5` no INI + o jogo ter plugin que suporte — e o FPS base
   precisa aguentar (abaixo de ~40 FPS base, artefatos, como o vídeo mostrou).
8. **Driver NVIDIA:** 591.86+ testado pelo projeto; nosso 616.56 ✅.

---

## 4. Procedimento de atualização (checklist)

1. Jogo **fechado** (ele reescreve config ao sair).
2. Backup: `version.dll` + `OptiScaler.ini` atuais → `.tp-bak`.
3. Baixar do **repo oficial** (não Telegram), conferir se é a build certa
   (SM86 = versão com "version.dll" para RTX 30; fork DLSSNR = zip standard, não o rtx40-mfg).
4. Substituir `version.dll`; **preservar o INI** (config atual está calibrada pro RDR2).
5. Teste do item 5 das regras acima.
6. Registrar versão nova em `docs/DECISOES.md`.

> **Futuro TurboPlay (v1.7+):** automatizar esta vigília — o watcher checar os
> Releases dos repos (GitHub API, sem login) e aplicar updates com backup+rollback
> como já faz com a instalação inicial. Ficou registrado como backlog.
