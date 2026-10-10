# Rotas de decisão do TurboPlay — por jogo

## RE3 (resident evil 3, 2020)

- EXE: `re3.exe`.
- Motivo da rota OptiFG: o jogo embarca os DLLs do DLSS-G na pasta, então o
  classificador reporta `fg_native=True`. Mas o jogo **nunca** chama
  `slDLSSGSetState` (jogo pré-DLSS3). O log da sessão confirma zero chamadas +
  FPS medido ~44 (delta 22.4 ms entre presents). Rotas delegativas (`dlssg`,
  `nvngxfg`) ficam paradas.
- Rota escolhida: `fg_output = fsrfg`, `replacement = FFX`, `HUDFix = true`.
- Por que o pré-launch antes regrava `dlssg`: o `reconfigure_optiscaler` revalidava
  o INI a cada jogo e sobrescrevia o `fg_output` que viera do perfil. Agora o
  perfil decide e o pré-launch mantém o valor do perfil (mesma origem).
- Limite do OptiFG (da wiki do OptiScaler): experimental; pode haver ghosting de
  HUD ou instabilidade ao alternar FG. Se o HUD duplique, ajustar o HUDFix Limit
  no menu do Insert. Se crashar ao ligar FG, trocar a rota pra FFX pura sem
  replacement.

## RDR2

- Stack: fork DLSS5+MFG (repack comunitário) + SM86, com `Spoofing/Dxgi=false` e
  força `settings.xml → DX12` (Vulkan não tem FG injetável).
- Comportamento observado: o jogo tem FG nativa e a rota `dlssg` funciona quando
  o jogo pede. Mas os testes mostraram que o proxy SM86 é necessário para destravar
  MFG em cima do DLSS-G.

## Mercado de decisor (jogos pré-DLSS3 da Capcom/RE Engine)

Lista explícita: `re2.exe`, `re3.exe`, `re7.exe`, `re8.exe`, `dmc5.exe`.

Para esses: rota OptiFG independente do `fg_native` (porque os DLLs parados não
garantam FG real). Para os demais jogos DX12 da série 20/30/40: rota
`DLSSG` (delegativa) com `FGNvngxReplacement`.

## Limites comuns a todos

- Anti-cheat: NOOP absoluto.
- Game Pass/MS Store (MSIX): NOOP — pasta protegida, injeção quebra assinatura.
- Pasta sem escrita: NOOP com motivo.
- SO não DX12: NOOP (rota alternativa futura).

## Estado do teste RE3

- Build 2.6 aplicada e reiniciada (processo ativo).
- `pytest tests/` e `compileall` limpos.
- INI no disco conferido: `FGOutput = fsrfg`, `FGNvngxReplacement = FFX`,
  `[OptiFG] HUDFix = true` nas seções certas.
- Não verificável daqui: se o OptiFG gera frames no seu teste (Overlay → FG → Active)
  e se o HUD fica íntegro.

## Mods

- Save 100% (armas/desbloqueios): instalado com backup dos 7 saves originais
  → `TurboPlay/backups/re3_saves_originais/`.
- Manifest: `turboinstall.mods.json` na pasta de saves (registra nome, arquivo
  fonte, arquivos copiados, sobrescritas).
- A reversão do save modificado hoje é pelo backup manual (ou `remove_mod`
  programático na GUI no futuro).

## Repo

- `https://github.com/Saaimingo/TurboPlay`
- Branch: `v2.6-fg-re3-optifg`
- README: agora documenta mods, OptiFG RE3, pyproject, onde fica o INI e os
  limites conhecidos.
