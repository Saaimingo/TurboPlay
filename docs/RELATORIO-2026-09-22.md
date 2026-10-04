# 📋 Relatório de Sessão — 22/09/2026 · DLSS 5 NR + MFG no RDR2 (fork v0.8.7)

> Sessão autorizada pelo Saimon ("Sim, instalar"). Todos os passos com backup e rollback.
> Complementa: `docs/RELATORIO-2026-09-21.md` · Decisões: **D12** (supersede parcial do D11).

---

## 1. Gatilho da sessão

Saimon comparou o menu do vídeo do Tech Games (OptiScaler com seção **DLSS Neural
Rendering**, Pre-SR, Multipass, NR FP8) com o nosso RDR2 — o nosso não tinha nada disso.
Causa: o vídeo usa o **fork `wilsjo2/OptiScaler-DLSSNR-PreSR-Multipass`** (overlay mostra
`OptiScaler v0.8.7-final`), que nós só tínhamos extraído/auditado (0.7.6), não instalado.
Além disso, RE Requiem (jogo do vídeo) tem DLSS+FG **nativa**; o RDR2 precisa da ponte
completa (Enabler/SM86) — caso mais difícil.

## 2. Descobertas técnicas do dia (importantes)

1. **O MFG NVIDIA NÃO estava realmente ativo no RDR2.** Log do Enabler (20:42):
   `UseFsrOnly=true` + `Priming DLSSG module: nvngx_dlssg.dll not found` → backend
   **FSR 3.1B embutido** gerava os frames. A cadeia SM86 estava *armada* (spoof ok,
   `FrameGeneration.Available=1`), mas **contornada** pelo Enabler. A "validação" de
   ontem provava a cadeia armada até o gate — não o gerador em uso.
2. **O doc do fork veda a coexistência que imaginamos:** modo `External` não serve pra
   RTX 30 ("Do not use this mode when you need OptiScaler to replace DLSSG with FSR FG
   on an RTX 30 card"). A rota correta documentada: **fork como OptiScaler único**
   (SR + NR + FG `dlssg`) + **proxy SM86 externo** como `version.dll`.
3. **O "HashMismatch" do `nvngx_dlssnr.dll` era esperado:** hash local `e67dee20…`
   bate com o **pinned `E67DEE…`** da tabela do fork (build cross-gen ShortFuse p/
   RTX 20/30/40); a assinatura NVIDIA inválida é comportamento documentado dessa build
   modificada — o hash é a garantia. Risco do D9 rebaixado. (165MB, origem: pacote
   Tech Games auditado ontem.)
4. A mensagem `Vulkan based application detected` do Enabler hoje era **misdetection**
   dele — o jogo segue em DX12 (SM86 logou `dlssg-310.9-d3d12-sm86`).

## 3. O que foi instalado (com verificação)

| Peça | Fonte | Verificação |
|---|---|---|
| Fork DLSSNR **v0.8.7** zip standard | GitHub oficial wilsjo2 (release 21/09) | SHA-256 `329694af…` = SHA256SUMS oficial; 57/57 arquivos OK dentro do zip |
| **Streamline SDK 2.14.1** (6 DLLs p/ `FGOutput=dlssg`) | NVIDIA-RTX/Streamline oficial | SHA-256 do zip `92c4d954…` = pinado no doc do fork; 6 DLLs com **Authenticode Válida, NVIDIA** |
| `nvngx_dlssnr.dll` 310.8 cross-gen | pacote local auditado 21/09 | hash `e67dee20…` = pinado no fork p/ RTX 30 |
| `nvngx_dlssg.dll` 310.9.1.0 | do Streamline SDK | assinatura NVIDIA válida ✓ |

**Arquitetura final no RDR2 (D12):**
- `dxgi.dll` = **fork v0.8.7** (`OptiScaler v10.0.0-dev (a8eac0c4)`)
- `version.dll` = proxy SM86 0.3.5 (**intocado**)
- `OptiScaler/streamline/` = sl.interposer, sl.common, sl.dlss_g, sl.reflex, sl.pcl, nvngx_dlssg + licenças
- `nvngx_dlssnr.dll` (165MB) na raiz do jogo
- `OptiScaler/` backend (amd_fidelityfx, libxess, nvfp4…) + `Licenses_DLSSNR/`
- **Enabler removido** (dxgi.dll dele, INI, logs) → backup `_tp-bak4/`

**Config aplicada ao INI do fork** (edição por seção, conferida no log):
`Dx12Upscaler=dlss` · `[FrameGen] Enabled=true / FGInput=upscaler / FGOutput=dlssg /
FGNvngxReplacement=None` · `[DLSSG] InterpolationCount=1` (2x total; 3x/4x = 2/3) ·
`[V-Sync] OverrideVsync=true / ForceVsync=false` · `[Log] LogToFile=true / LogLevel=2` ·
`[DlssNr] Enabled=true / RunBeforeSR=true / Passes=1 / WorkingScale=1.0`

## 4. Validação (logs, jogo rodando)

- `OptiScaler.log`: fork carregado, **config lida corretamente**, `nvngx_dlssnr.dll found`,
  Streamline inicializado, `DLSSG_Dx12::CreateSwapchain1 Max supported interpolations: 3`,
  **0 erros** após 3+ min rodando, VRAM estável (~1.8 GB no menu).
- `dlssg_sm86/logs/backend_5160.jsonl`: `install executed_on_sm86_hardware=true` (RTX 3060),
  runtime 310.9.1.0, **`route_active=true`**, hooks NGX ok,
  **`mfg_capability: original_max 5 → reported_max 3 (changed=true)`** — o proxy está
  mediando a runtime do fork exatamente conforme nosso teto de 4x,
  `FrameGeneration.Available=1` · `FeatureInitResult=1` · `DLSSG.MultiFrameCountMax=3`.
- `cu_chain_launch status -14 / entries 0`: informativo nesta fase (nada a reescrever
  antes da criação da feature FG no gameplay).

## 5. Pendências (ordem)

1. **Menu do fork:** no jogo, tecla `Insert` deve abrir o overlay com a seção
   **DLSS Neural Rendering** (igual ao vídeo). Testar input (se travar:
   `[Hotfix] ManualInputPolling=true`).
2. **FG em gameplay:** entrar no jogo e confirmar 2x (primeira execução compila
   shaders — demora). Depois testar 3x/4x (`InterpolationCount=2/3`).
3. **NR visual:** comparar com NR on/off (custo FP16 na 3060 é alto; se pesado,
   `WorkingScale=0.5` ou Passes=0 → NR off).
4. **FPS on/off** (pendente de ontem) — AGS no gameplay.
5. **TurboPlay:** perfil novo "fork DLSSNR" no pipeline (não reaplicar overrides do
   0.9.4 nem reinstalar Enabler em jogos com fork) + atualizar GUIA-ATUALIZACOES
   (v0.8.7 é a referência agora; v0.8.8 saiu 22/09 mas "No games were launched").

## 6. Rollback (se algo der errado)

1. Jogo fechado, apagar `dxgi.dll`, `OptiScaler/`, `OptiScaler.ini`,
   `nvngx_dlssnr.dll`, `Licenses_DLSSNR/`.
2. Restaurar de `_tp-bak4/`: `dxgi.dll` (Enabler), `dlss-enabler.ini`,
   `OptiScaler.ini`, `D3D12_Optiscaler/`, logs e `Remove_OptiScaler.bat`.
3. `version.dll` (SM86) nunca foi tocado — cadeia FSR3-FG do estado de ontem volta intacta.

## 7. Caminhos

- Jogo: `D:\Games\SAMBOX-Vfull\sistema\roms\ps5\sistema\roms\ps4eps5installars\Red Dead Redemption 2`
- Backup desta sessão: `<jogo>\_tp-bak4\` · Backups antigos: `.tp-bak`, `.tp-bak2`, `.tp-bak3`
- Downloads verificados: `D:\Games\MFG-NVIDIA-DLSS5\_downloads\optiscaler_dlssnr_087\` (zip + extraído +
  SHA256SUMS) e `_downloads\streamline-sdk-2.14.1\`
- Decisão: `docs/DECISOES.md` D12 · Guia de vigília: `docs/GUIA-ATUALIZACOES-MFG-DLSS5.md`
