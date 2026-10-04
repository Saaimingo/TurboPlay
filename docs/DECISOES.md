# 📝 TurboPlay — Registro de Decisões

Formato: data · decisão · contexto · consequências

---

## 2026-09-21 · D1 · Produto: zero interação, decisão automática

**Decisão:** o software decide sozinho a stack por jogo+GPU; nenhuma UI técnica.
**Contexto:** público de 90% não-programadores, vindos de console; o valor é
"funciona e o usuário nem sabe". Qualquer tela técnica destrói a proposta.
**Consequências:** logs e painel oculto p/ diagnóstico; falhas viram rollback
silencioso; documentação voltada a desenvolvedores, não usuários.

## 2026-09-21 · D2 · Segurança: anti-cheat = jogo intocável

**Decisão:** detecção de anti-cheat (BattlEye, EAC, Denuvo, VMProtect) bloqueia
qualquer modificação, sem exceção e sem opt-in.
**Contexto:** modos online podem banir; um único caso de ban destrói a reputação
do produto. RDR2 story é ok; GTA Online não.
**Consequências:** base de perfis precisa flag `online_safe`; mensagens ao
usuário (se existirem) nunca prometem "funciona em tudo".

## 2026-09-21 · D3 · Fontes: releases oficiais + hash pinado

**Decisão:** OptiScaler, DLSS Enabler e dlssg_for_sm86 baixados só dos releases
oficiais no GitHub, com SHA-256 pinado por versão no repositório de perfis.
**Contexto:** DLLs injetáveis são vetor de malware; o ecossistema já teve
"DLSS 5 manager" falso (aviso no repo faisalkindi/DLSS5oneclick).
**Consequências:** atualização de componente = PR mudando hash; nunca baixar
"latest" às cegas em runtime.

## 2026-09-21 · D4 · Tecnologia: Python stdlib no core

**Decisão:** MVP em Python puro (stdlib) — sem pip install.
**Contexto:** máquina alvo é de jogador comum; dependências são atrito e risco.
**Consequências:** parsing de PE/VDF feito à mão (struct/json); empacotamento
futuro via PyInstaller → exe único.

## 2026-09-21 · D5 · SAMBOX/RetroBat como cidadão de primeira classe

**Decisão:** o scanner entende a estrutura de `.bat` do RetroBat/SAMBOX e
classifica jogos PC nativos escondidos lá (ex.: RDR2 em `roms/ps5/...`).
**Contexto:** descoberta feita nesta máquina — o ecossistema BR de "pacotões"
usa RetroBat como frontend universal; nenhum concorrente trata isso.
**Consequências:** parsing de .bat e heurística de launcher vs emulador no scanner.

## 2026-09-21 · D6 · Conhecimento: a stack é camadas, não um pacote

**Decisão:** modelar perfis pelas CAMADAS (proxy SM86 / DLSS Enabler / OptiScaler /
ReShade) e não por "produto pronto" (DLSS5 Manager).
**Contexto:** investigação 21/09/2026 — dlssg_for_sm86 é proxy de runtime NVIDIA
não-modificada (kernels reais em Ampere, bit-exact); DLSS Enabler simula FG em
jogos sem nativa; OptiScaler escolhe entrada/saída. Combinar camadas cobre
DX12 com/sem FG, com/sem DLSS.
**Consequências:** perfis declaram camadas + flags (dll name, ini keys);
verificação por logs de cada camada.

## 2026-09-21 · D7 · DLSS 5 (neural render) fora do MVP

**Decisão:** MVP não aplica DLSS 5 NR — só MFG/FG + upscaling.
**Contexto:** NR é pesado (perde FPS em Ampere sem upscaler por trás), depende
de ReShade+RenoDX por jogo, e nem todo jogo tem mod. Custo/benefício baixo no MVP.
**Consequências:** classe de jogo "DLSS5-capable" fica no classificador para uso
futuro; roadmap pós-MVP.

---

## 2026-09-21 · D8 · Vulkan bloqueia FG → pipeline força DX12

**Decisão:** perfis de jogos RAGE (RDR2) forçam `kSettingAPI_DX12` no settings.xml
e usam `FGInput=upscaler + FGOutput=fsrfg` (Nukems exige DLSS-G nativo, que o
jogo não tem). Mecanismo novo: overrides de INI com escopo `Seção/Chave` +
reconfiguração leve de jogos já otimizados (perfis evoluem sem reinstalar).
**Contexto:** teste real 21/09 17:49 — jogo em Vulkan hookou só o DLSS2; FG zero.
**Consequências:** DX12 passa a ser pré-condição verificada; aprendizados de
teste viram código no mesmo dia.

---

## 2026-09-21 · D9 · Pacote Tech Games (fork DLSSNR v0.7.6): GUARDAR com ressalvas

**Decisão:** não apagar o RAR "OptiScaler_NVIDIA_MFG_6X" — auditar, extrair em
`_downloads/optiscaler_dlssnr_076/` e tratar como candidato a upgrade experimental.
**Contexto:** auditoria achou runtimes NVIDIA oficiais assinadas (dlssg/dlssd válidas),
`nvngx_dlssnr.dll` com HashMismatch (modificado pós-assinatura) e `version.dll` de fork
sem hash público. O próprio doc do fork nega ser unlocker de RTX 30 sozinho.
**Consequências:** adoção só após teste com rollback; NR é o caminho do DLSS 5 no RDR2;
MFG da série 30 continua dependendo do proxy SM86 + DLSS Enabler.

## 2026-09-21 (noite) · D10 · Sem autostart no Run key do Windows

**Decisão:** TurboPlay não se registra mais na chave Run (HKCU). Modo residente
fica disponível apenas manualmente (`TurboPlay.exe watch --silent`).
**Contexto:** o Windows Defender classificou o conjunto exe + atalho + Run key
como comportamento de malware (falso positivo de PyInstaller não assinado) e
quarentenou o executável e o atalho 2x (16:41 e 19:44). A Run key era o gatilho
da heurística — removida, o exe e o atalho sobreviveram estáveis.
**Consequências:** jogador abre o TurboPlay pelo atalho quando quer; watcher em
tempo real continua funcionando com a GUI aberta. Se um dia quisermos
autostart de volta: assinatura de código (certificado) ou pasta Startup com
script .bat (menos flagrado) — testar com cautela.

## 2026-09-21 (noite) · D11 · Arquitetura de hooks no RDR2: version=SM86, dxgi=Enabler

**Decisão:** com DLSS Enabler + proxy SM86 no mesmo jogo: SM86 fica como
`version.dll` (o jogo importa e sua tabela de forward exige o nome original —
o release oficial só traz a variante version.dll); Enabler entra renomeado
como `dxgi.dll` (renomear é oficialmente documentado pelo autor); o
OptiScaler standalone (`winmm.dll` 0.9.4) e o Nukems são REMOVIDOS (com
backup .tp-bak2) porque o Enabler embute o OptiScaler 0.9.5-pre3.
**Contexto:** os slots version/winmm já estavam ocupados; imports do RDR2.exe
(version, winmm, dinput8, wintrust) mapeados via parser PE; releases do SM86
no GitHub NÃO têm binários (só fonte) — a variante dinput8 não existe no
pacote local, e renomear entre nomes de sistema quebraria o forward.**Consequências:** pipeline acha zip do Enabler em _downloads/dlss-enabler/ e repete a instalação sozinho em outros jogos (enabler.py reescrito); jogos com Enabler não recebem reconfiguração de optiscaler.ini (INI pertence ao OptiScaler embutido); bridge MFG NVIDIA fechada no RDR2.

## 2026-09-22 · D12 · RDR2: fork DLSSNR v0.8.7 como OptiScaler único — Enabler removido (supersede parcial do D11)

**Decisão:** instalar o fork `wilsjo2/OptiScaler-DLSSNR-PreSR-Multipass` **v0.8.7** (zip standard,
hash oficial verificado) como OptiScaler único do RDR2 em `dxgi.dll`, com FG via **Streamline 2.14.1
oficial** (`FGOutput=dlssg`, 6 DLLs em `OptiScaler/streamline/`) e DLSS 5 Neural Render ligado
(1 passe, pre-SR). O DLSS Enabler 4.9 foi REMOVIDO (backup `_tp-bak4`). O proxy SM86 0.3.5
permanece como `version.dll`, intocado.

**Contexto:** descoberta do dia — o log do Enabler (`UseFsrOnly=true`, `Priming DLSSG: not found`)
mostrou que ontem o FG real rodava como **FSR 3.1B embutido**, nunca como DLSS-G NVIDIA; a cadeia
SM86 estava armada mas contornada. O doc do próprio fork veda o modo External pra RTX 30 ("Do not
use this mode when you need OptiScaler to replace DLSSG with FSR FG on an RTX 30 card") e documenta
a rota correta: OptiScaler único com saída dlssg + unlocker SM86 externo. O `nvngx_dlssnr.dll`
local bateu o hash pinado `E67DEE…` (build cross-gen ShortFuse p/ RTX 20/30/40) — a assinatura
NVIDIA "inválida" é comportamento documentado pra essa build; o hash é a garantia (rebaixa o risco
do D9).

**Consequências:** o slot `dxgi.dll` voltou a ser do OptiScaler (agora o fork, v10.0.0-dev a8eac0c4);
os INIs passam a ser do fork (seções `[FrameGen]`/`[DLSSG]`/`[DlssNr]`); validação por 3 logs
(`OptiScaler.log`, `dlssg_sm86/logs`, SL dentro do OptiScaler.log); o Enabler continua disponível
em `_downloads/dlss-enabler/` pra outros jogos, mas o pipeline do TurboPlay precisa de perfil novo
para jogos com fork (não reaplicar overrides antigos de OptiScaler 0.9.4 nem reinstalar Enabler);
rollback total via `_tp-bak4` (restaurar conteúdo + apagar dxgi.dll/OptiScaler*/nvngx_dlssnr.dll).
Referência: `docs/RELATORIO-2026-09-22.md`.

---

## 2026-10-04 · D13 · O fork DLSSNR entra no motor de perfis (fecha a pendência do D12)

**Decisão:** `profiles.py` passa a decidir `DLSS5_MFG` (camadas `DLSSNR_FORK` + `SM86`) para
NVIDIA série 20/30/40 em jogo DX12 — antes ele só conhecia a rota D11 (OptiScaler 0.9.4 + FSR-FG).
`applier.py` ganha `apply_dlssnr_fork()`, que instala o fork v0.8.7 em `dxgi.dll`, as 6 DLLs do
Streamline 2.14.1 em `OptiScaler/streamline/` e a runtime `nvngx_dlssnr.dll`, e escreve o INI do
fork por seção.

**Contexto:** o D12 validou essa stack **à mão** no RDR2 mas o produto nunca a conheceu — rodar
`apply` instalaria a stack antiga por cima da que funciona. Além disso os caches reais estão em
`optiscaler_dlssnr_087/extracted/` e `streamline-sdk-2.14.1/extracted/bin/x64/` (não na raiz), e a
runtime NR **não vem no fork 087**: vem do pacote Tech Games 076.

**Consequências:** `verify_fork_integrity()` roda antes de qualquer escrita e confere SHA-256 contra
os hashes pinados (fork `329694af…`, NR `e67dee20…` — este medido nesta máquina); com hash divergente
não instala. SM86 só entra se `version.dll` estiver livre. Estado/rollback passaram a gravar os
arquivos e pastas corretos (`OptiScaler/`, `Licenses_DLSSNR/`, `nvngx_dlssnr.dll`).

## 2026-10-04 · D14 · `run_full` instalava stack só no primeiro jogo

**Decisão:** `layers_done` passa a ser criado **por jogo** (`_apply_layers(g, p, set())`) em vez de
compartilhado no laço.

**Contexto:** defeito encontrado na revisão de 04/10 — o `set` era criado antes do `for`, então
`layers_done.add(layer)` na 1ª iteração fazia `if layer in layers_done: continue` pular **todas**
as camadas em todos os jogos seguintes. Reproduzido: 3 jogos → 1 instalado. `optimize_one` (botão
▶ JOGAR) não era afetado.

**Consequências:** coberto por teste de regressão (`test_pipeline_layers_per_game`) **validado por
mutação** — reintroduzir o defeito faz o teste falhar com `receberam=['Jogo 1']`.

## 2026-10-04 · D15 · Game Pass / Microsoft Store é NOOP, não injetado

**Decisão:** jogos MSIX são detectados (`providers.scan_xbox`, via GameConfig) e marcados
`protected_install=True`; `decide()` devolve NOOP com o motivo. Nenhuma escrita é tentada.

**Contexto:** pedido explícito de cobertura "de qualquer provedor, incluindo Game Pass Ultimate".
Games da Store vivem em `C:\Program Files\WindowsApps`, com ACL do TrustedInstaller e assinatura de
pacote. Injetar `dxgi.dll` ali invalida a assinatura e **o jogo deixa de abrir** — não é que "não
funciona bem", é que quebra. Prometer otimização aqui seria mentira; a conduta honesta é detectar e
explicar.

**Consequências:** o mesmo vale para qualquer pasta sem escrita: `is_writable()` grava e apaga um
arquivo de teste — não confia em ACL nem em `is_admin()`. O NOOP traz o motivo e vira ação para o
jogador ("rode como administrador ou mova o jogo").

## 2026-10-04 · D16 · Descoberta multi-provedor (`providers.py`)

**Decisão:** novo módulo centraliza Steam, Xbox/Store, Epic, GOG, pastas custom e SAMBOX, com dedup
por executável. Pastas custom vêm de `%LOCALAPPDATA%\TurboPlay\custom_folders.txt` (uma por linha) —
é a rede de segurança para jogo fora de qualquer loja.

**Contexto:** o `README` e a `ARQUITETURA` prometiam scanner de pastas custom desde a v1.0; o enum
`CUSTOM` existia em `models.py` e nenhum código o produzia. Steam na máquina tem **duas** bibliotecas
(`C:` e `D:\SteamLibrary`) — a segunda era descoberta corretamente, mas a lista de jogos vinha só do
scanner antigo.

**Consequências:** executáveis conhecidos de emulador/frontend (`duckstation`, `retroarch`,
`rpcs3`, …) nunca entram na fila de otimização — isso eliminou os falsos positivos `controle-ps1` /
`controle-ps2`, que o pipeline poderia ter otimizado automaticamente sem prompt.

## 2026-10-04 · D17 · Watcher sem perda de evento; autostart sem registro

**Decisão:** `_signature()` passa a usar **mtime por subpasta de 1º nível** + contagem de itens
(debounce 60s). O autostart sai da chave `Run` e passa a usar atalho `.lnk` na pasta **Inicializar**
do Windows.

**Contexto:** o `_snapshot()` antigo comparava só o mtime da raiz. Medido em disco real: download da
Steam cria subpasta em `common\` → dispara; ROM nova cai em `roms\ps1\` e **não** mudava `roms\` →
evento perdido. A pasta Inicializar é a via suportada, não toca registro e não acopla exe a
persistência — que era exatamente o gatilho da heurística do Defender (D10).

**Consequências:** `--dry-run` disponível em `apply` e `watch` para ver o que seria feito sem
escrever nada (verificado: `installed.json` idêntico antes/depois). `autostart on|off|status`
substitui a integração de registro.
