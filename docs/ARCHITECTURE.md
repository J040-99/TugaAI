# Arquitetura — TugaAI

> Documento técnico. Atualizado a 2026-09-28 a partir do estado do repositório
> (`package.json` 0.11.4, branch `minha-feature`).

## 1. Visão geral

Monorepo com frontend JavaScript/TypeScript e backend Python, ligados por uma API REST +
WebSockets. Herdada do Open WebUI 0.11.4, com customizações do TugaAI assinaladas ao longo do
documento.

```
┌──────────────────────────────────────────────────────────────────┐
│  NAVEGADOR / PWA (telemóvel ou desktop)                          │
│  SvelteKit 2 + Svelte 5 + Vite 5 + Tailwind 4 + i18next (PT-PT) │
│  Workers: pyodide.worker.ts, KokoroWorker.ts                     │
└───────────────▲───────────────────────────────▲──────────────────┘
                │ REST /api/v1/*  +  Socket.IO  │
┌───────────────┴───────────────────────────────┴──────────────────┐
│  BACKEND — FastAPI (Python 3.11/3.12)                            │
│  backend/open_webui/                                             │
│   ├─ main.py / config.py / env.py / constants.py / tasks.py      │
│   ├─ routers/    (30 routers REST)                               │
│   ├─ utils/      (lógica partilhada: brain, auth, models, …)     │
│   ├─ models/ + internal/db.py + migrations/ (SQLAlchemy + Alembic)│
│   ├─ storage/    (local, S3, GCS, Azure)                         │
│   ├─ retrieval/  (RAG: 9 vector stores)                          │
│   ├─ tools/ + socket/                                            │
│   └─ data/webui.db   ← SQLite (ficheiros + config + utilizadores)│
└──────────────────────────────────────────────────────────────────┘
```

## 2. Stack

| Camada        | Tecnologia                                                                 |
| ------------- | -------------------------------------------------------------------------- |
| Frontend      | SvelteKit ^2.5.27, Svelte ^5.53, Vite ^5.4, TypeScript ^5.5, Tailwind ^4.0  |
| UI adicional  | TipTap 3/ProseMirror (editor), Yjs (colaboração), Mermaid, KaTeX, Chart.js, Vega, xterm, `@xyflow/svelte` |
| i18n          | i18next + `browser-languagedetector`, ~70 locales, `pt-PT` é o foco do fork |
| Execução Py.  | Pyodide (navegador) + `@pyscript/core`; `sql.js` para SQL no cliente        |
| Backend       | FastAPI 0.136, Uvicorn 0.51, Pydantic 2.13, python-socketio                 |
| BD            | SQLAlchemy 2.0 (async) + aiosqlite/psycopg + Alembic; SQLite por omissão    |
| IA            | `openai`, `anthropic`, `langchain-*`, `mcp`, `transformers`, `tiktoken`     |
| Áudio/visão   | `faster-whisper`, `onnxruntime`, `pillow`, `opencv`, `rapidocr`             |
| Almacenamento | `boto3`, `google-cloud-storage`, `azure-storage-blob`                       |
| Auth          | `ldap3`, `authlib`, PyJWT, bcrypt, argon2                                    |
| Ferramentas   | ruff (backend), prettier + eslint + svelte-check (frontend), pytest, vitest  |

Versões exigidas: Python `>=3.11,<3.13`; Node `>=18.13.0 <=22.x.x`.

## 3. Estrutura do repositório

```
C:\TugaAI\TugaAI\
├─ backend\
│  └─ open_webui\
│     ├─ main.py            # criação da app FastAPI
│     ├─ config.py, env.py  # carga de config (.env + BD)
│     ├─ routers\           # 30 endpoints (auths, chats, files, models, …)
│     ├─ utils\             # brain.py, model_reliability.py, rate_limit.py, …
│     ├─ models\            # modelos SQLAlchemy
│     ├─ internal\          # ligações à BD
│     ├─ migrations\        # Alembic
│     ├─ retrieval\, storage\, tools\, socket\
│     ├─ static\            # build do frontend servido em produção (favicon TugaAI)
│     └─ data\webui.db      # SQLite de desenvolvimento  ⚠ não versionar
├─ src\
│  ├─ app.html, app.css, tailwind.css
│  └─ lib\
│     ├─ apis\              # clientes REST por domínio (chats, files, models, …)
│     ├─ components\        # UI (admin, chat, layout, notes, playground, workspace, …)
│     ├─ stores\, types\, utils\, constants\   # constants.ts → APP_NAME = 'TugaAI'
│     ├─ i18n\              # index.ts (i18next) + locales\pt-PT\translation.json
│     ├─ pyodide\           # createPyodideWorker.ts, pyodideSandboxHost.ts
│     └─ workers\           # pyodide.worker.ts, KokoroWorker.ts
├─ src\routes\
│  ├─ (app)\  # admin, automations, brain*, c/[id], calendar, channels, folders,
│  │          # home, notes, playground, spending*, tutoriais*, workspace  (* = TugaAI)
│  ├─ auth\, error\, s\[id]\, watch\
│  └─ +layout.svelte        # SW PWA TugaAI, limpeza de SWs do upstream
├─ static\                  # pyodide, assets, manifest.json (TugaAI), sw.js, sql.js
├─ test\                    # pytest: brain, fallback, rate-limit, i18n, reliability
├─ scripts\                 # restart-tugaai.ps1*, setup-tugaai-config.py*, prepare-pyodide.js, …
├─ docs\                    # PRD, ARCHITECTURE, RULES, DESIGN, TASKS, MEMORY, SECURITY
└─ docker-compose*.yaml (8) + Dockerfile + Makefile
```

## 4. Backend

### 4.1 Routers (`backend/open_webui/routers/`)

`analytics, audio, auths, automations, calendar, channels, chats, configs, evaluations, files,
folders, functions, groups, images, knowledge, memories, models, notes, notifications, ollama,
openai, pipelines, prompts, retrieval, scim, skills, tasks, terminals, tools, users, utils`

Rotas expostas em `/api/v1/...`. A autenticação passa por `Depends(get_verified_user)`.

### 4.2 Utils relevantes

| Ficheiro                  | Função                                                                |
| ------------------------- | --------------------------------------------------------------------- |
| `utils/brain.py`          | Modo Cérebro: prompt, parsing, fichas, paginação e busca de fichas     |
| `utils/model_reliability.py` | Selo de fiabilidade/fallback por modelo                            |
| `utils/rate_limit.py`     | Detecção de limite de taxa e nova tentativa                           |
| `utils/memory.py`         | Memória persistente do assistente (upstream)                          |
| `utils/code_interpreter.py` | Código executado no servidor                                        |
| `utils/mcp\`, `utils/telemetry\` | integração MCP e observabilidade                              |

### 4.3 Persistência

- **Base de dados**: SQLite por omissão em `backend/data/webui.db` (PostgreSQL via extra
  `postgres` do `pyproject.toml`). Tabelas: utilizadores, chats, ficheiros, `config` (chaves de
  configuração da app), etc. Migrações Alembic em `migrations/`.
- **Configuração**: combinada de `.env` + tabela `config` (a aplicar com
  `scripts/setup-tugaai-config.py`).
- **Ficheiros**: carregados em `storage/` (local por omissão; S3/GCS/Azure opcionais).
- **Vetores**: 9 vector stores suportados (ChromaDB por omissão; PGVector, Qdrant, Milvus,
  Elasticsearch, OpenSearch, Pinecone, S3Vector, Oracle 23ai).

### 4.4 Configuração ativa do TugaAI (`.env`)

```
WEBUI_NAME=TugaAI          PORT=8080
WEBUI_AUTH=true            ENABLE_SIGNUP=true
ENABLE_DIRECT_CONNECTIONS=true   # BYOK (OpenRouter/chaves diretas)
ENABLE_OLLAMA_API=false    # Ollama desativado por omissão
CORS_ALLOW_ORIGIN=…        FORWARDED_ALLOW_IPS=…
ANONYMIZED_TELEMETRY / SCARF_NO_ANALYTICS / DO_NOT_TRACK
```

## 5. Frontend

### 5.1 Rotas próprias do TugaAI

| Rota          | Ficheiro                                    | Descrição                                    |
| ------------- | ------------------------------------------- | -------------------------------------------- |
| `/tutoriais`  | `src\routes\(app)\tutoriais\+page.svelte`   | Guia PT: chave OpenRouter, 1.ª conversa, PWA, gastos |
| `/brain`      | `src\routes\(app)\brain\+page.svelte`       | Grelha de fichas de memória com pesquisa/filtros |
| `/spending`   | `src\routes\(app)\spending\+page.svelte`    | Consumo e custos                             |

### 5.2 Camada de dados do cliente

`src/lib/apis/` agrupa clientes REST por domínio (`chats`, `files`, `models`, `configs`,
`knowledge`, `notes`, …). A página `/brain` chama diretamente:

- `GET /api/v1/files/brain?page&limit&q&category` → `BrainListResponse {items, total, page, limit}`
- `GET /api/v1/files/brain/state` → estado da reflexão periódica

### 5.3 i18n

- `src/lib/i18n/index.ts`: i18next, deteção `querystring → localStorage → navigator`,
  fallback `en-US`, cache em `localStorage` (chave `locale`).
- Recursos carregados com `import(...)` dinâmico; `settings-translations.ts` permite *overrides*.
- Chaves aproximadas: **pt-PT 3662**, **en-US 3614**, **pt-BR 3535** (linhas-chave).
- Comando: `npm run i18n:parse` (config em `i18next-parser.config.ts`).

### 5.4 Execução de Python no navegador

`static/pyodide/` contém a distribuição Pyodide + wheels (numpy, pandas, matplotlib, scikit-learn,
openai, …). `scripts/prepare-pyodide.js` (`pyodide:fetch`) corre antes de `dev`/`build`.
`src/lib/pyodide/createPyodideWorker.ts` isola a execução em `src/lib/workers/pyodide.worker.ts`;
`pyodideSandboxHost.ts` trata da sandbox.

## 6. Modo Cérebro — fluxo técnico

```
upload → extração de texto (routers/files.py)
           │
           ▼  (background, asyncio)
utils/brain.py · build_prompt()      ← template JSON, texto truncado a 12 000 chars
           │  chamada ao LLM (BRAIN_MODEL ou 1.º modelo; BRAIN_ORGANIZE=true)
           ▼
parse_brain_payload()  →  file.data['brain']
     { title, summary, tags[], category, date, entities[] }
           │  falha do LLM ⇒ grava nada, upload continua
           ▼
GET /api/v1/files/brain   (routers/files.py · BrainListResponse)
     · filtra/PAGINA na BD via func.json_extract(...) sobre File.data
     · JSON LIKE em filename/title/summary/tags/entities
           │
           ▼
/pbrain  … página /brain (cards, category filter, "carregar mais")
```

Pontos de projeto relevantes:

- `iter_brain_cards(page_size=200)` varre os ficheiros em páginas, descartando o conteúdo
  extraído — escala para grandes volumes.
- `card_matches(card, q, category)` faz o filtro de texto livre e categoria no servidor.
- **Cuidado** (comentado no código): em `routers/files.py`, importar `File as FileRow` do
  SQLAlchemy — `File(...)` sem alias é o construtor do FastAPI.
- Categorias: `memory | person | place | document | other`; entidades: `person | place | topic`.

## 7. Arranque e ambientes

| Ambiente     | Comando                                                          |
| ------------ | ---------------------------------------------------------------- |
| Windows dev  | `backend\start_windows.bat` (backend :8080) + `npm run dev` (:5173) |
| Tudo de uma  | `powershell -File scripts\restart-tugaai.ps1` (flags: `-SkipBackend`, `-SkipFrontend`, `-NoPrompt`, `-FrontendPort`) |
| Config inicial | `python scripts\setup-tugaai-config.py`                        |
| Makefile     | `install`, `remove`, `start`, `startAndBuild`, `stop`, `update`  |
| Docker       | `Dockerfile` + `docker-compose.yaml`, `.api`, `.data`, `.gpu`, `.amdgpu`, `.a1111-test`, `.otel`, `.playwright` |
| Produção     | `npm run build` → estático servido pelo backend (`open_webui/static`) |

`restart-tugaai.ps1` (244 linhas): termina só processos do TugaAI, pede elevação UAC se
necessário, lê `PORT` do `.env`, localiza o nvm em `%LOCALAPPDATA%\Author Software\nvm`, arranca
backend/frontend com logs em `%TEMP%\tugaai-logs\`, espera HTTP 200 (90 s backend / 120 s
frontend — `npm run dev` inclui `pyodide:fetch`).

## 8. Qualidade de código

| Área        | Ferramenta                                                            |
| ----------- | --------------------------------------------------------------------- |
| Python      | ruff (line-length **120**, aspas simples, seleção `E,F,W,I,UP,C90,Q,ICN`, `max-complexity 10`); prettier de backend via `ruff-format` |
| Pre-commit  | `.pre-commit-config.yaml`: `ruff --fix backend` + `ruff-format backend` (v0.15.5) |
| Frontend    | prettier (`useTabs`, `singleQuote`, `printWidth 100`, `endOfLine lf`, plugin svelte), eslint (`eslint:recommended` + TS + svelte + cypress), `svelte-check` |
| Testes      | `pytest` em `test/` (injeta `sys.path` para `backend/`, `DATA_DIR` temporário); `vitest` (`npm run test:frontend`); cypress |
| Comandos    | `npm run lint` (eslint + svelte-check + pylint backend), `npm run format`, `npm run format:backend` |
| CI          | `.github/workflows/`: `backend`, `frontend`, `docker`, `regression`, `release`, `release-pypi` |

## 9. Relação com o upstream

- `upstream` → <https://github.com/open-webui/open-webui.git>; `origin` →
  <https://github.com/J040-99/TugaAI.git>.
- Branches: `main`, `minha-feature` (ativa em desenvolvimento).
- Commits próprios assinalados por prefixo (`feat:`, `chore:`, `fix:`) e pelo merge
  `8bd8b4fac Merge pull request #29960 from open-webui/dev`.
- Personalizações localizadas em: `constants.ts`, `app.html`, `+layout.svelte` (SW),
  rotas `brain`/`tutoriais`/`spending`, `utils/brain.py`, `routers/files.py`, `static/*`
  (manifestos e ícones TugaAI), `scripts/restart-tugaai.ps1`, `scripts/setup-tugaai-config.py`.
- **Não alterar**: `static/BRANDING.md`, `static/README.md` e ficheiros de atribuição
  (`LICENSE`, `LICENSE_HISTORY`, `LICENSE_NOTICE`) — obrigação de licença.

## 10. Riscos técnicos conhecidos

1. **Divergência do upstream**: merges frequentes são obrigatórios; as customizações devem
   permanecer em ficheiros próprios ou marcadas com comentários `TugaAI:` para minimizar conflitos.
2. **Serviço worker**: `+layout.svelte` limpa SWs do upstream preservando o `/sw.js` do TugaAI
   (chave `sessionStorage 'tugaai-sw-reloaded'`) — não remover essa lógica.
3. **`/brain` em volume**: a paginação tem de permanecer no servidor; nunca carregar todas as
   fichas para o browser.
4. **Chaves duplicadas no `translation.json`**: `pt-PT` contém as chaves duplicadas
   `Add tag`/`Add Tag` (o PowerShell 5.1 nem consegue parseá-lo) — limpar quando possível.
5. **Estado por commitar**: 4 ficheiros modificados em `minha-feature` (ver `docs/TASKS.md`).
