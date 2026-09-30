# Regras — TugaAI

Regras de trabalho no repositório `C:\TugaAI\TugaAI`. Aplicam-se a pessoas e a agentes de IA.
Em caso de conflito, esta lista tem prioridade sobre hábitos individuais.

---

## 1. Regra de ouro

> **O TugaAI é um fork do Open WebUI.** Toda a alteração deve ser fácil de repetir num merge do
> upstream. Prefere-se adicionar ficheiros próprios e comentários `TugaAI:` a editar em massa
> ficheiros herdados.

## 2. Licença e atribuição

1. **Nunca remover** a atribuição ao Open WebUI: `LICENSE`, `LICENSE_HISTORY`, `LICENSE_NOTICE`,
   `static/BRANDING.md`, `static/README.md` e as respetivas cópias em `static\static\`.
2. O nome exibido é `TugaAI (Open WebUI)` (`WEBUI_NAME=TugaAI` + sufixo acrescentado pelo backend
   em `env.py`; manifestos com o mesmo padrão).
3. Textos próprios do TugaAI devem creditar o projeto original quando apropriado (ex.: rodapé de
   `/tutoriais`).

## 3. Git

1. **Branches**: `main` = estado estável; `minha-feature` = desenvolvimento ativo. Trabalhar em
   branch e fazer *merge*/PR para `main`.
2. **Mensagens de commit** — prefixo convencional, em inglês (padrão do repositório):
   `feat:`, `fix:`, `refac:`, `perf:`, `chore:`, `doc:`, `i18n:`, `test:`, `build:`, `ci:`.
   Exemplos reais: `feat: brain mode phase 2 — /brain page and periodic reflection`.
3. Commits pequenos e atómicos; nunca misturar customizações do TugaAI com um merge do upstream.
4. **Não commitar**: `.env`, `backend/data/`, `node_modules/`, `.svelte-kit/`, `build/`,
   `__pycache__/`, `*.log` (ex.: `backend/devserver.*.log`), `vite.config.ts.timestamp-*`.
5. Antes de commitar: `git status`, `git diff` e `git log --oneline -10` — só staged do que é
   pretendido.
6. **Não forçar push**, não fazer *amend* de commits já publicados, não apagar histórico.

## 4. Estilo — backend (Python)

- **ruff**: line-length **120**, aspas simples, organização de imports (`I`), regras `UP`, `C90`
  (`max-complexity 10`), `Q`, `ICN`.
- Formatação: `ruff format` (`npm run format:backend`).
- Pre-commit já está configurado (`ruff --fix backend` + `ruff-format backend`) — **correr
  `pre-commit install`** numa máquina nova e nunca saltar os hooks.
- Comentários e docstrings em **português de Portugal** nos ficheiros próprios do TugaAI
  (`utils/brain.py`, `routers/files.py` — já é assim).
- Não introduzir dependências novas sem justificação; adicionar ao `pyproject.toml`
  (opcionais no grupo respetivo).

## 5. Estilo — frontend (Svelte/TS)

- **prettier**: tabs (`useTabs: true`), aspas simples, sem *trailing commas*, `printWidth 100`,
  `endOfLine: lf`, plugin `prettier-plugin-svelte`.
- **eslint**: `eslint:recommended` + `@typescript-eslint` + `svelte` + `cypress` + `prettier`.
- Correr `npm run lint` antes de commitar (inclui `svelte-check` e pylint do backend).
- Usar as abstrações existentes: stores de `src/lib/stores`, clientes de `src/lib/apis`,
  constantes de `src/lib/constants` (`APP_NAME = 'TugaAI'`).

## 6. Internacionalização (obrigatório)

1. **Nenhuma string visível em texto duro** em componentes — usar `const i18n = getContext('i18n')`
   e `$i18n.t('...')`.
2. Chaves novas em inglês (chave = texto inglês, valor = tradução) e **tradução em
   `pt-PT/translation.json` sempre**.
3. Traduções do TugaAI só em `pt-PT` — não alterar os outros ~70 locales (herdados).
4. Rodar `npm run i18n:parse` após adicionar chaves; verificar chaves duplicadas.
5. Texto dirigido ao utilizador: português europeu ("utilizador", "telemóvel", "ecrã",
   "ficheiro", "palavra-passe"), não brasileiro.

## 7. Testes

1. Toda a lógica nova em Python deve ter teste em `test/` (padrão: `test_*.py`, pytest).
2. Os testes usam `sys.path.insert(... backend)` e `DATA_DIR` temporário — **não** partilhar a BD
   real.
3. Cobertura mínima atual: `test_brain.py`, `test_model_fallback.py`,
   `test_model_reliability.py`, `test_rate_limit_retry.py`, `test_error_messages_i18n.py`.
4. Comandos: `pytest test/` e `npm run test:frontend` (vitest).

## 8. Segurança e segredos

1. Chaves de API **nunca** no repositório: só em `.env` (ignorado) ou na BD.
2. Nunca registar tokens, chaves OpenRouter ou conteúdo de `.env` em logs/mensagens de commit.
3. Não enfraquecer `WEBUI_AUTH`, cookies seguros ou validação de acesso ao alterar
   `routers/`/`utils/auth.py`.
4. Alterações a autenticação/permissões exigem revisão extra.

## 9. Regras específicas do TugaAI

1. **Nome**: `TugaAI` (com maiúsculas como em `TugaAI`); no código `tugaai` apenas em chaves de
   armazenamento (ex.: `tugaai.recentModels`, `tugaai-sw-reloaded`).
2. **PWA**: preservar o registo do SW em `+layout.svelte` (mantém o `/sw.js` do TugaAI ao limpar
   SWs do upstream).
3. **Modo Cérebro**: o LLM é opcional — qualquer falha tem de ser degradada graciosamente (nunca
   falhar o upload). Manter filtro/paginação no servidor (`GET /api/v1/files/brain`).
4. **`routers/files.py`**: importar `File as FileRow` do SQLAlchemy — `File` sem alias colide com
   `File(...)` do FastAPI.
5. **Ambiente Windows**: scripts próprios em PowerShell devem funcionar com PowerShell 5.1
   (sem recursos de versões mais novas).

## 10. Documentação

- Documentos vivos em `docs/`: `PRD.md`, `ARCHITECTURE.md`, `RULES.md`, `DESIGN.md`,
  `TASKS.md`, `MEMORY.md`, `SECURITY.md`.
- Atualizar `docs/TASKS.md` ao concluir tarefas e `docs/MEMORY.md` quando uma decisão mudar.
- Não criar ficheiros de documentação duplicados na raiz.

## 11. Comandos essenciais

```powershell
# arranque completo (Windows)
powershell -ExecutionPolicy Bypass -File scripts\restart-tugaai.ps1

# configuração inicial da BD
python scripts\setup-tugaai-config.py

# qualidade
npm run lint                # eslint + svelte-check + pylint
npm run format              # prettier (frontend)
npm run format:backend      # ruff format (backend)
pytest test/                # testes python

# upstream
git fetch upstream
git merge upstream/main     # verificar conflitos em src/lib/i18n e rotas próprias
```
