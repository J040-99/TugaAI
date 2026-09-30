# PRD — TugaAI

| Campo       | Valor                                                             |
| ----------- | ----------------------------------------------------------------- |
| Produto     | **TugaAI** ("TugaAI (Open WebUI)")                                 |
| Versão do PRD | 1.0                                                             |
| Data        | 2026-09-28                                                         |
| Estado      | Em construção                                                      |
| Base        | Fork do [Open WebUI](https://github.com/open-webui/open-webui) 0.11.4 |
| Repositório | <https://github.com/J040-99/TugaAI>                                |

---

## 1. Resumo do produto

O **TugaAI** é uma instância self-hosted de IA, em português de Portugal, construída sobre o
Open WebUI. O utilizador liga a sua **chave própria OpenRouter** (BYOK — *bring your own key*),
conversa com qualquer modelo suportado pelo OpenRouter e instala a aplicação no telemóvel como
**PWA**, sem passar por lojas de aplicações.

Diferencial face ao Open WebUI de origem:

- **PT-PT como idioma principal** (interface, tutoriais e conteúdo gravados em português europeu);
- **Mobile primeiro** (PWA instalável, `share_target`, tema escuro, ícones e splash próprios);
- **Modelo de uso BYOK**, com Ollama desativado por omissão e páginas de gestão de gastos;
- **Modo Cérebro** — organização automática dos ficheiros carregados em fichas de memória
  pesquisáveis (feature própria, não existe no upstream).

## 2. Contexto e problema

Existe procura por uma interface de IA simples, em português, que:

1. Não exija conta num serviço externo nem subscrição (usa chave OpenRouter do próprio utilizador);
2. Funcione bem num telemóvel, instalada no ecrã inicial;
3. Corra num servidor próprio (casa, NAS, VPS), mantendo os dados sob controlo do utilizador;
4. Ajude quem está a começar: tutoriais passo-a-passo e controlo de gastos.

O Open WebUI satisfaz (3) e boa parte de (1) e (2), mas é anglofocado, complexo de configurar de
raiz e não traz organização automática de documentos.

## 3. Objetivos

| #   | Objetivo                                                          | Métrica                                                |
| --- | ----------------------------------------------------------------- | ------------------------------------------------------ |
| O-1 | Arranque único e simples no Windows                               | `scripts/restart-tugaai.ps1` sobe backend + frontend   |
| O-2 | Interface integralmente em PT-PT                                  | ≥ 99 % das chaves de `pt-PT` traduzidas                 |
| O-3 | Utilização confortável em telemóvel                               | PWA instalável, primeira conversa em < 5 min           |
| O-4 | Custos visíveis                                                    | Página `/spending` com consumo por modelo/utilizador   |
| O-5 | Documentos organizados automaticamente                            | Fichas de memória geradas após cada upload              |
| O-6 | Manter-se atualizável face ao upstream                            | Merge de `upstream` sem perda das customizações         |

### Não-objetivos (para esta fase)

- Ser um serviço comercial multi-tenant com faturação;
- Suportar Ollama/locais por omissão (mantido `ENABLE_OLLAMA_API=false`);
- Reimplementar funcionalidades do upstream (canais, calendário, notas, terminais) — são herdadas;
- Aplicação nativa iOS/Android (usa-se PWA).

## 4. Personas

**P1 — Utilizador final (João, 25–55 anos)**
Tem chave OpenRouter, usa o telemóvel como dispositivo principal. Quer conversar, pedir ajuda com
documentos e perceber quanto gasta. Não tem conhecimentos de administração de servidores.

**P2 — Administrador do servidor (Ana)**
Instala e mantém a instância TugaAI numa máquina Windows/NAS. Editar `.env`, correr scripts,
fazer merges do upstream, gerir utilizadores e permissões.

**P3 — Agente/assistente de desenvolvimento (AI)**
Agente que trabalha sobre o repositório. Precisa de contexto persistente (`docs/MEMORY.md`),
regras (`docs/RULES.md`) e do estado atual das tarefas (`docs/TASKS.md`).

## 5. Requisitos funcionais

Prioridades: **M**ust / **S**hould / **C**ould / **W**on't (nesta versão).

### 5.1 Conta e ligações

| ID      | Prioridade | Requisito                                                                 |
| ------- | ---------- | ------------------------------------------------------------------------- |
| RF-01   | M          | Registo de conta ativo por omissão (`ENABLE_SIGNUP=true`) e autenticação (`WEBUI_AUTH=true`). |
| RF-02   | M          | Ligação direta a fornecedores compatíveis com OpenAI (BYOK): `ENABLE_DIRECT_CONNECTIONS=true`. |
| RF-03   | M          | Ollama desativado por omissão (`ENABLE_OLLAMA_API=false`), sem custo de configuração inicial. |
| RF-04   | S          | Configuração inicial reproduzível: `scripts/setup-tugaai-config.py` aplica as chaves de config na BD. |

### 5.2 Interface e conteúdo

| ID      | Prioridade | Requisito                                                                 |
| ------- | ---------- | ------------------------------------------------------------------------- |
| RF-10   | M          | Nome do produto "TugaAI" visível em título, manifestos e `WEBUI_NAME`.    |
| RF-11   | M          | Idioma por omissão PT-PT, com deteção de língua do navegador e fallback `en-US`. |
| RF-12   | M          | Rota `/tutoriais` com guia passo-a-passo: chave OpenRouter, primeira conversa, instalação PWA, controlo de gastos. |
| RF-13   | M          | PWA instalável: `manifest.json` com `lang: pt-PT`, `share_target`, `theme_color #171717`. |
| RF-14   | S          | Página `/spending` com consumo e custos por modelo.                       |
| RF-15   | S          | Traduções próprias do TugaAI adicionadas apenas a `pt-PT` (não ao resto dos locales). |

### 5.3 Modo Cérebro (feature própria)

| ID      | Prioridade | Requisito                                                                 |
| ------- | ---------- | ------------------------------------------------------------------------- |
| RF-20   | M          | Após upload e extração de texto, gerar em *background* uma ficha JSON: título, resumo, tags, categoria, data, entidades. |
| RF-21   | M          | A ficha é guardada em `file.data['brain']` e nunca bloqueia o upload — se o LLM falhar, o ficheiro fica como antes. |
| RF-22   | M          | Listagem paginada e pesquisável via `GET /api/v1/files/brain` (paginação e filtro feitos na base de dados). |
| RF-23   | S          | Página `/brain` com grelha de fichas, filtro por categoria (`memory`, `person`, `place`, `document`, `other`), pesquisa e paginação por "carregar mais". |
| RF-24   | S          | Reflexão periódica ("brain mode phase 2"): síntese recorrente do estado da base de memória. |
| RF-25   | C          | Configuração por env: `BRAIN_ORGANIZE` (default `true`) e `BRAIN_MODEL`.  |

### 5.4 Fiabilidade

| ID      | Prioridade | Requisito                                                                 |
| ------- | ---------- | ------------------------------------------------------------------------- |
| RF-30   | M          | Fallback entre modelos e repetição em caso de limite de taxa (`rate_limit`). |
| RF-31   | M          | Erros apresentados de forma amigável, com ações de repetir e selo de fiabilidade do modelo. |
| RF-32   | S          | Testes automatizados cobrindo cérebro, fallback, rate-limit e mensagens de erro i18n. |

## 6. Requisitos não funcionais

- **Desempenho**: a página `/brain` nunca deve transferir o volume total de fichas — apenas a
  página pedida (filtro/paginação no servidor, `json_extract` na BD).
- **Escalabilidade**: iteração sobre fichas em páginas (`iter_brain_cards`, 200 por página),
  descartando o conteúdo extraído a cada página.
- **Portabilidade**: Windows como ambiente principal de desenvolvimento; Docker disponível para
  outros sistemas.
- **Versões**: Python `>=3.11,<3.13`; Node `>=18.13 <=22.x`.
- **Privacidade**: telemetria desativável (`ANONYMIZED_TELEMETRY`, `SCARF_NO_ANALYTICS`,
  `DO_NOT_TRACK`); a chave OpenRouter é do utilizador e o TugaAI não a expõe.
- **Segredos**: `.env` nunca é versionado; `.env.example` documenta as variáveis.

## 7. Regras de negócio

1. O TugaAI apresenta-se como "TugaAI (Open WebUI)" — a atribuição ao Open WebUI não pode ser
   removida (ver `LICENSE`, `LICENSE_HISTORY`, `static/BRANDING.md`).
2. A chave OpenRouter nunca é devolvida ao cliente para leitura (apenas substituição).
3. O brain mode é *best-effort*: falha do LLM não invalida o upload nem a extração de texto.
4. Categorias de ficha restritas a: `memory`, `person`, `place`, `document`, `other`.
5. Entidades restritas a: `person`, `place`, `topic` (máx. 10 por documento).
6. Texto enviado ao LLM do cérebro truncado a 12 000 caracteres (`BRAIN_MAX_CONTENT_CHARS`).

## 8. Critérios de aceitação (MVP)

- [ ] `scripts/restart-tugaai.ps1` sobe backend (porta 8080) e frontend (porta 5173) sem intervenção.
- [ ] Novo utilizador regista-se, liga chave OpenRouter e envia a primeira mensagem em < 5 min,
      seguindo `/tutoriais`.
- [ ] Interface a 100 % em PT-PT nas rotas próprias (`/tutoriais`, `/brain`, `/spending`).
- [ ] Upload de um PDF gera ficha de memória visível em `/brain` com título, resumo e tags.
- [ ] `/brain` pesquisa e filtra por categoria devolvendo resultados paginados.
- [ ] `pytest test/`, `npm run lint` e `npm run format:backend` passam.

## 9. Fora de âmbito desta versão

Multi-tenant com faturação; apps nativas; marketplace de plugins próprio; suporte oficial a
Outros fornecedores além dos compatíveis com OpenAI/OpenRouter; tradução completa dos ~70 locales
do upstream.

## 10. Referências

- `README.md` — documentação de características herdadas do Open WebUI.
- `docs/ARCHITECTURE.md` — arquitetura técnica.
- `docs/TASKS.md` — estado atual e roadmap.
- `CHANGELOG.md` — histórico upstream.
