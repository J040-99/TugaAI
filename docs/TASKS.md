# Tarefas — TugaAI

Estado do trabalho. **Atualizar este ficheiro sempre que uma tarefa muda de estado.**
Data da última atualização: **2026-09-28** · Branch ativa: `minha-feature`

---

## 1. Legenda

- ✅ Concluída · 🔄 Em curso · ⏳ Pendente · ⛔ Bloqueada

## 2. Trabalho por commitar (estado do working tree)

> `git status` a 2026-09-28 — **4 ficheiros modificados, 304 inserções / 75 remoções**, tudo
> relacionado com a **fase 2 do Modo Cérebro**.

| Ficheiro                                 | Δ            | Conteúdo da alteração                                            | Estado |
| ---------------------------------------- | ------------ | ---------------------------------------------------------------- | ------ |
| `backend/open_webui/routers/files.py`    | +76          | `GET /api/v1/files/brain` (`BrainListResponse`) com paginação/filtro na BD; `GET .../brain/state` | 🔄     |
| `backend/open_webui/utils/brain.py`      | +214         | `iter_brain_cards()` paginado (200/página), `card_matches()`, `query_brain_cards()`            | 🔄     |
| `src/routes/(app)/brain/+page.svelte`    | +88          | Paginação por "carregar mais" (`PAGE_SIZE=20`), estado de reflexão, filtros                     | 🔄     |
| `src/lib/i18n/locales/pt-PT/translation.json` | +1       | Chaves novas do estado/cérebro                                    | 🔄     |

**Ação imediata**: terminar a fase 2, correr `pytest test/` + `npm run lint`, commitar com
mensagem tipo `feat: brain mode phase 2 — server-side paging for /brain`.

## 3. Concluído (commits próprios do TugaAI)

| Commit     | Mensagem                                                        |
| ---------- | ---------------------------------------------------------------- |
| `4060ef5bc` | `feat: brain mode phase 2 — /brain page and periodic reflection` |
| `e6c1eaca9` | `feat: brain mode — automatic file organisation`                 |
| `10403c538` | `chore: TugaAI branding assets and restart script`               |
| `8d11cd245` | `feat: friendly error UI, retry actions and model reliability badge` |
| `2b1c18e29` | `feat: model fallback, rate-limit retries and friendly error messages` |

Funcionalidades entregues:

- ✅ Identidade TugaAI (nome, manifestos, favicon/logo, splash, `WEBUI_NAME`).
- ✅ PWA mobile com service worker próprio (`static/sw.js` + registo em `+layout.svelte`).
- ✅ `/tutoriais` — guia PT de ligação da chave OpenRouter, primeira conversa, instalação e gastos.
- ✅ `/spending` — consumo e custos.
- ✅ Modo Cérebro fase 1: organização automática de ficheiros (`utils/brain.py`).
- ✅ Fallback de modelos, retries em rate-limit, erros amigáveis, selo de fiabilidade.
- ✅ Scripts Windows: `restart-tugaai.ps1`, `setup-tugaai-config.py`.
- ✅ Testes: `test_brain.py`, `test_model_fallback.py`, `test_model_reliability.py`,
      `test_rate_limit_retry.py`, `test_error_messages_i18n.py`.

## 4. Em curso

| #   | Tarefa                                                                  | Prioridade | Notas                                            |
| --- | ----------------------------------------------------------------------- | ---------- | ------------------------------------------------ |
| 1   | Concluir e commitar **brain mode fase 2** (ver §2)                       | 🔴 Alta    | 4 ficheiros por commitar; testar escala/paginação |
| 2   | Testar `GET /api/v1/files/brain` com volume (≥ 1 000 fichas)            | 🔴 Alta    | Garantir que nada carrega o volume total p/ browser |
| 3   | Rever estado da reflexão periódica (`/brain/state`) — cancelamento e erros | 🟠 Média | RF-24 do PRD                                     |

## 5. Pendente (backlog)

### Produto

| #   | Tarefa                                                                 | Prioridade |
| --- | ---------------------------------------------------------------------- | ---------- |
| 4   | Revisar tradução `pt-PT` completa (3662 chaves vs 3614 em `en-US`)      | 🔴 Alta    |
| 5   | Limpar chaves duplicadas `Add tag`/`Add Tag` no `pt-PT`                | 🟠 Média   |
| 6   | Tela de arranque/onboarding guiada (além de `/tutoriais`)              | 🟠 Média   |
| 7   | Página `/brain` — vista de detalhe da ficha + abrir o ficheiro original | 🟠 Média   |
| 8   | Exportação/backup das fichas de memória                                 | 🟡 Baixa   |

### Manutenção

| #   | Tarefa                                                                 | Prioridade |
| --- | ---------------------------------------------------------------------- | ---------- |
| 9   | Sincronizar com `upstream` (open-webui) — merge e reconciliação de conflitos | 🔴 Alta |
| 10  | Atualizar `docs/*` após cada fase (inclui este ficheiro)                | 🟠 Média   |
| 11  | Ativar workflows de lint desativados (`.github/workflows/*.disabled`)   | 🟡 Baixa   |
| 12  | Verificar cobertura dos testes de i18n (falta de chaves em `pt-PT`)     | 🟡 Baixa   |
| 13  | Revistar `.env.example` — refletir variáveis novas (`BRAIN_*`)          | 🟠 Média   |
| 14  | `docs/SECURITY.md` — rever com o fork em mente                          | 🟡 Baixa   |

## 6. Definição de pronto

Uma tarefa só é ✅ quando:

1. `pytest test/` passa;
2. `npm run lint` e `npm run format:backend` passam;
3. strings novas traduzidas em `pt-PT/translation.json`;
4. commit convencional criado (ver `docs/RULES.md` §3);
5. este ficheiro e `docs/MEMORY.md` atualizados, se aplicável.

## 7. Histórico de alterações deste documento

| Data       | Alteração                        |
| ---------- | -------------------------------- |
| 2026-09-28 | Criação a partir do estado git   |
