# Relatório de auditoria local — TurboPlay

**Data:** 10/10/2026
**Branch:** `feat/turboplay-optiscaler-ui`
**Base observada antes do registro:** `89c7ce6` (`docs: notas operacionais do RE3 e do mercado de decisão`)

## Escopo

Foi solicitada uma revisão do estado atualizado do projeto, comparando código, testes, dependências, documentação e decisões com o escopo definido. A instrução proibiu executar jogos, tocar instalações/saves, instalar ferramentas/dependências, habilitar Computer Use, alterar a configuração do Hermes, fazer scans contra caminhos reais de jogos, ou publicar/mesclar uma release.

A revisão cobriu o pipeline, perfis, providers, GUI, capas locais, watcher, CLI, testes, `pyproject.toml`, README e documentação de arquitetura/decisões. A política definida pelo titular foi preservada: `DLSS5_MFG` para as GPUs alvo em DX12, com ou sem FG nativa, mantendo a exceção RE Engine pré-DLSS3 descrita no código e nos testes.

## Correções e documentação registradas

- **Capas locais:** validação PNG/GIF com Pillow, rejeição de conteúdo inválido, fallback visual genérico por jogo e cache. O cache de validação compara SHA-256 dos bytes, além da identidade do arquivo, para detectar alteração in-place que preserve tamanho, `mtime_ns` e inode. Não há download de artwork externo. A GUI carrega imagem estática para GIF; animação não foi validada como requisito.
- **Seletor da capa:** proteção contra chamada reentrante; a flag é liberada em `finally`.
- **Probe de escrita:** `is_writable()` passou a usar nome temporário exclusivo (`NamedTemporaryFile`, `delete=True`) em vez de nome fixo, e o teste verifica que um arquivo preexistente chamado `.tp_write_probe.tmp` permanece intacto. A função continua criando e removendo um probe na pasta consultada — portanto, scans/dry-runs ainda podem escrever transitoriamente em diretórios reais detectados e não devem ser executados neles sem autorização/revisão específica.
- **Perfis e dry-run:** explicações de `FGOutput` foram alinhadas com a configuração efetiva, preservando a exceção RE Engine; a mensagem do dry-run não afirma que reconfigurou o jogo.
- **Documentação:** README, arquitetura e decisões esclarecem dependência Pillow e efeitos locais de descoberta/scan/watch/dry-run, inclusive probe e possível extração de RAR para cache local.

## Evidências registradas na sessão

Os comandos abaixo e resultados foram reportados pela sessão TurboPlay; esta nota não os reexecuta:

- `python tests/test_pipeline.py` — **77/77 PASS**, exit code 0 após corrigir a revalidação de capa modificada in-place. O teste novo falhou antes da correção (**76/77**) e passou depois.
- `python -m unittest tests.test_providers_encoding tests.test_dry_run` — **2 testes, OK**.
- `python -m unittest discover -s tests -v` — **2 testes, OK**; essa descoberta executa os dois testes unittest separados, não substitui o runner próprio de `test_pipeline.py`.
- `python -m compileall -q src tests` e `git diff --check` — exit code 0; persistiram avisos do Git sobre conversão LF/CRLF.
- `ast.parse(..., feature_version=(3,8))` em 28 arquivos Python — PASS. Python 3.8 real não foi instalado nem executado.
- Build PyInstaller em pasta temporária — exit code 0. Artefato reportado: `C:\Users\saimi\AppData\Local\Temp\TurboPlay-audit-dist-pillow\TurboPlay.exe` (29.785.109 bytes). O EXE não foi executado; o build não comprova funcionamento. O log também listou módulos opcionais/condicionais ausentes, incluindo `olefile`.
- Revisão independente estritamente estática do cache SHA-256 — sem falha estática identificada. Limitações: leitura/hash de até 20 MiB a cada consulta e possível corrida se os bytes mudarem após a leitura. Outros pareceres registrados aprovaram estaticamente a proteção de reentrância e o uso de probe exclusivo; a cobertura explícita de GPU permaneceu mais forte para RTX 30 do que para RTX 20/40.

## Incidente de escrita transitória — registro obrigatório

Em uma etapa anterior, scans invocaram `is_writable()` e criaram/removeram `.tp_write_probe.tmp` nas pastas reais de RE3, The Last of Us Part II e Red Dead Redemption 2, contrariando a restrição comunicada. Uma verificação posterior confirmou o probe ausente nos três caminhos. Não há evidência de alteração permanente de arquivos de jogo, saves ou instalação. Na auditoria documentada aqui, não foram executados scans/probes/dry-runs contra pastas reais de jogos; os testes de escrita usaram `TemporaryDirectory`.

## Estado e limites

- **Automação local:** os resultados acima sustentam as verificações reportadas; não equivalem a uma garantia absoluta nem a aprovação de comportamento em runtime.
- **Jogos:** RE3 não foi aberto. Boot/partida, DLSS 5, geração de quadros e logs reais continuam sem evidência e dependem de teste dentro do jogo.
- **Computer Use:** não foi habilitado nem exercitado.
- **Build:** gerado em Temp, não executado nem validado como distribuição funcional.
- **Python 3.8:** somente gramática sintática foi verificada; sem runtime real.
- **Git:** alterações registradas no commit `b207773` e enviadas para `origin/feat/turboplay-optiscaler-ui`; a leitura de volta confirmou o mesmo hash local e remoto. Sem merge, PR ou release.

## Arquivos alterados na árvore local observada

Modificados: `README.md`, `docs/ARQUITETURA.md`, `docs/DECISOES.md`, `pyproject.toml`, `src/gui.py`, `src/pipeline.py`, `src/profiles.py`, `src/providers.py`, `src/turboplay.py`, `src/watcher.py`, `tests/test_pipeline.py`.
Novos: `src/covers.py`, `tests/test_dry_run.py`, `tests/test_providers_encoding.py`, este relatório.
