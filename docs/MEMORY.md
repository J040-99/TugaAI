# Memória — TugaAI

Contexto persistente do projeto para humanos e agentes de IA. **Ler antes de qualquer alteração
no repositório.** Atualizado a 2026-09-28.

> Quando uma decisão mudar, **editar este ficheiro no mesmo commit**.

---

## 1. O que é isto

- **TugaAI** = fork do [Open WebUI](https://github.com/open-webui/open-webui) (versão base
  **0.11.4**), personalizado para utilização em português de Portugal, mobile/BYOK.
- Localização: **`C:\TugaAI\TugaAI`** (atenção: existe uma pasta `C:\TugaAI` que só contém esta).
- Remotes: `origin` = <https://github.com/J040-99/TugaAI.git> ·
  `upstream` = <https://github.com/open-webui/open-webui.git>
- Branches: `main` (estável) e `minha-feature` (**ativa**, é onde se trabalha).
- Ambiente: **Windows**, PowerShell 5.1. Node **não está no PATH global** — o nvm vive em
  `%LOCALAPPDATA%\Author Software\nvm` (o `restart-tugaai.ps1` trata disso).

## 2. Decisões que não devem ser revertidas

| # | Decisão | Onde |
| - | ------- | ---- |
| D1 | **BYOK/OpenRouter por omissão**: `ENABLE_DIRECT_CONNECTIONS=true`, `ENABLE_OLLAMA_API=false` | `.env`, `scripts/setup-tugaai-config.py` |
| D2 | **Atribuição ao Open WebUI mantida** — requisito de licença (`LICENSE`, `LICENSE_HISTORY`, `static/BRANDING.md`) | raiz, `static/` |
| D3 | **Nome `TugaAI`** no título/manifestos; o sufixo "(Open WebUI)" é acrescentado pelo backend | `src/app.html`, `static/manifest.json`, `env.py` |
| D4 | **Service worker próprio** preservado ao limpar SWs do upstream (chave `tugaai-sw-reloaded`) | `src/routes/+layout.svelte` |
| D5 | **Modo Cérebro é best-effort**: falha do LLM nunca falha o upload | `backend/open_webui/utils/brain.py` |
| D6 | **Paginação/filtro no servidor** para `/brain` (JSON extract na BD, nunca carregar tudo p/ browser) | `routers/files.py`, `brain/+page.svelte` |
| D7 | **PT-PT é o locale do TugaAI**; os outros ~70 locales são do upstream e não se toca | `src/lib/i18n/locales/` |
| D8 | **`File as FileRow`** em `routers/files.py` — `File` sem alias é o construtor do FastAPI | `routers/files.py` |
| D9 | Testes Python usam `DATA_DIR` temporário e injetam `backend/` no `sys.path` — não ligam à BD real | `test/*.py` |

## 3. Onde estão as coisas

| Preciso de…                       | Local                                                     |
| ---------------------------------- | --------------------------------------------------------- |
| …criar funcionalidade backend      | `backend/open_webui/routers/` + `utils/`                  |
| …lógica do cérebro                 | `backend/open_webui/utils/brain.py` (582 linhas)          |
| …rota nova do TugaAI               | `src\routes\(app)\<rota>\+page.svelte`                     |
| …chamar a API no cliente           | `src/lib/apis/`                                           |
| …traduzir                          | `src/lib/i18n/locales/pt-PT/translation.json` (`npm run i18n:parse`) |
| …constante de nome                  | `src/lib/constants.ts` → `APP_NAME`                       |
| …arrancar tudo no Windows          | `scripts/restart-tugaai.ps1`                               |
| …aplicar config inicial na BD      | `scripts/setup-tugaai-config.py`                           |
| …documentação viva                 | `docs/` (PRD, ARCHITECTURE, RULES, DESIGN, TASKS, MEMORY, SECURITY) |
| …testes                            | `test/` (pytest) — sem cobertura de rotas API              |

## 4. Estado conhecido (2026-09-28)

- **Por commitar**: 4 ficheiros da *fase 2 do brain mode* (`files.py` +76, `brain.py` +214,
  `brain/+page.svelte` +88, `pt-PT/translation.json` +1). Detalhe em `docs/TASKS.md` §2.
- Últimos commits próprios: `4060ef5bc` (brain phase 2), `e6c1eaca9` (brain), `10403c538`
  (branding), `8d11cd245` (erros amigáveis), `2b1c18e29` (fallback de modelos).
- Último merge do upstream: `8bd8b4fac Merge pull request #29960 from open-webui/dev`.
- Portas por omissão: **backend 8080** (`PORT` no `.env`), **frontend 5173** (Vite).
- Traduções: `pt-PT` 3662 linhas-chave vs `en-US` 3614 — **`pt-PT` tem chaves duplicadas
  `Add tag`/`Add Tag`** (o PowerShell 5.1 falha ao parsear o JSON por causa disso).

## 5. Comandos que funcionam

```powershell
# arranque completo (backend :8080 + frontend :5173, com logs em %TEMP%\tugaai-logs)
powershell -ExecutionPolicy Bypass -File scripts\restart-tugaai.ps1
  # flags: -SkipBackend  -SkipFrontend  -NoPrompt  -FrontendPort <n>

# config inicial (BYOK on, Ollama off, signup on)
python scripts\setup-tugaai-config.py

# testes e qualidade
pytest test/
npm run lint            # eslint + svelte-check + pylint
npm run format:backend  # ruff format
npm run i18n:parse      # sincronizar chaves i18n
```

## 6. Armadilhas conhecidas

1. **`C:\TugaAI` ≠ `C:\TugaAI\TugaAI`** — o projeto real é o segundo.
2. **Parêntesis em caminhos**: em PowerShell usar `-LiteralPath 'src\routes\(app)\...'`, caso
   contrário o `(app)` é interpretado como comando.
3. **`node` não está no PATH** — usar o nvm de `%LOCALAPPDATA%\Author Software\nvm` ou os scripts.
4. **Não editar ficheiros de atribuição do upstream** (ver §2, D2).
5. **Não remover** o bloco do service worker em `+layout.svelte` (D4).
6. **`npm run dev` demora** (~120 s) porque executa `pyodide:fetch` antes (`scripts/prepare-pyodide.js`).
7. **Merge do upstream**: os conflitos mais prováveis são `src/lib/i18n/locales/*`, `src/lib/components/`
   e `routers/` — resolver mantendo as customizações marcadas com `TugaAI:`.
8. **`.env` não versionar**; o `.env.example` está desatualizado face às variáveis novas (`BRAIN_*`).

## 7. Glossário

| Termo           | Significado                                                         |
| --------------- | ------------------------------------------------------------------- |
| **BYOK**        | *Bring your own key* — o utilizador fornece a chave OpenRouter       |
| **Modo Cérebro**| Organização automática de ficheiros em fichas de memória (`brain`)  |
| **Ficha**       | Objeto JSON em `file.data['brain']` (título, resumo, tags, categoria, data, entidades) |
| **Reflexão**    | Síntese periódica do estado da base de memória (fase 2)             |
| **Upstream**    | Repositório oficial `open-webui/open-webui`, de onde vem o código   |
| **Locales**     | Ficheiros de tradução em `src/lib/i18n/locales/`                    |

## 8. Documentos relacionados

`PRD.md` (o que se constrói) · `ARCHITECTURE.md` (como funciona) · `RULES.md` (como trabalhar) ·
`DESIGN.md` (como se vê) · `TASKS.md` (o que falta) · `SECURITY.md` (segurança herdada).
