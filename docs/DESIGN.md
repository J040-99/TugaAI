# Design — TugaAI

Diretrizes visuais e de experiência do TugaAI. Complementa `DESIGN` com `PRD.md` (requisitos) e
`ARCHITECTURE.md` (implementação). Atualizado a 2026-09-28.

---

## 1. Identidade

| Elemento       | Valor                                                                 |
| -------------- | --------------------------------------------------------------------- |
| Nome           | **TugaAI**                                                            |
| Nome completo  | "TugaAI (Open WebUI)" (manifestos, `WEBUI_NAME` + sufixo do backend)  |
| Nome curto     | "TugaAI" (`short_name`)                                               |
| Descrição      | "TugaAI — assistente de IA com OpenRouter, otimizado para mobile. Powered by Open WebUI." |
| Idioma         | `pt-PT` (`lang` do documento e dos manifestos)                        |
| Repositório    | <https://github.com/J040-99/TugaAI>                                   |

### Assets

- `static/logo.png` / `static/static/logo.png` (27 797 B, idêntico ao `favicon.png`)
- `static/static/favicon.svg` — SVG com `aria-label="TugaAI"` (**também copiado para
  `backend/open_webui/static/favicon.svg`**, que é o servido em produção)
- `static/static/`: `favicon.ico`, `favicon-96x96.png`, `apple-touch-icon.png`,
  `web-app-manifest-192x192.png`, `web-app-manifest-512x512.png`, `splash.png`, `splash-dark.png`
- `src/app.html` → `<title>TugaAI</title>`
- `src/lib/constants.ts` → `export const APP_NAME = 'TugaAI';` (atribuição "Open WebUI" é
  acrescentada automaticamente pelo backend)

> **Regra de licença**: os ficheiros `BRANDING.md`/`README.md` de `static/` pertencem ao Open
> WebUI e **não devem ser reescritos** — a personalização faz-se pelos assets, manifestos e
> `WEBUI_NAME`.

## 2. Tema e cor

- **Fundo por omissão**: `#171717` (`theme_color` e `background_color` dos manifestos) — modo
  escuro como estado natural do produto.
- Paleta: neutros escuros do Tailwind, com destaques semânticos (ver §4).
- Modo claro/escolhido pelo utilizador continua a ser suportado pelo upstream — manter
  consistência `dark:` em qualquer componente novo.
- Ícones próprios: manter `user.png`, ícones de splash e as imagens de `static/assets/`.

## 3. Mobile primeiro (PWA)

1. **Manifest** (`static/manifest.json` e `static/static/site.webmanifest`):
   - `display: standalone`, `lang: "pt-PT"`, cores `#171717`;
   - ícones maskable 192/512, `apple-touch-icon`;
   - `share_target` com parâmetro `shared` — partilhar texto/diretamente para o TugaAI.
2. **Service worker próprio** (`static/sw.js`), registado em `src/routes/+layout.svelte` com a
   chave `sessionStorage 'tugaai-sw-reloaded'` — limpa SWs do upstream **sem** apagar o nosso.
3. **Splash**: `splash.png` / `splash-dark.png` no arranque instalado.
4. Alvos de toque: áreas ≥ 44 px; navegação principal acessível com uma mão (menu/avatar no canto
   inferior esquerdo, conforme os textos de `/tutoriais`).
5. Verificar em: Chrome Android, Safari iOS (limitações de SW), desktop.

## 4. Sistema de cores semânticas (Modo Cérebro)

Usado em `src\routes\(app)\brain\+page.svelte` — reutilizar estes pares para novas etiquetas:

| Categoria  | Fundo claro            | Texto claro      | Variante dark            |
| ---------- | ---------------------- | ---------------- | ------------------------ |
| `memory`   | `bg-amber-100`         | `text-amber-700` | `dark:bg-amber-500/15 dark:text-amber-300` |
| `person`   | `bg-sky-100`           | `text-sky-700`   | `dark:bg-sky-500/15 dark:text-sky-300`     |
| `place`    | `bg-emerald-100`       | `text-emerald-700` | `dark:bg-emerald-500/15 dark:text-emerald-300` |
| `document` | `bg-gray-100`          | `text-gray-700`  | `dark:bg-gray-500/15 dark:text-gray-300`   |
| `other`    | `bg-violet-100`        | `text-violet-700`| `dark:bg-violet-500/15 dark:text-violet-300` |

Entidades: `person` = sky, `place` = emerald, `topic` = gray (mesmo padrão).

## 5. Tipografia e conteúdo

- Herdada do Open WebUI (Tailwind + fontes em `static/assets/fonts/`) — não introduzir fontes novas
  sem necessidade.
- **Textos**: português europeu — *utilizador*, *telemóvel*, *ecrã*, *ficheiro*, *palavra-passe*,
  *ligação* (não "conexão"), *transportar/partilhar* (não "upload" em textos de leitura fácil).
- Títulos de página: `<página> · TugaAI` (ex.: `{$i18n.t('Spending')} · TugaAI`).
- Números/custos: formato europeu (`12,34 €`).
- Tom de voz: próximo e sem jargão; explicações curtas e passo-a-passo (ver `/tutoriais`).

## 6. Padrões de interface

| Padrão                     | Onde                                                                  |
| -------------------------- | --------------------------------------------------------------------- |
| Spinner ao carregar        | `src/lib/components/common/Spinner.svelte` (usado em `/brain`)         |
| Debounce de pesquisa       | `searchTimer` com `setTimeout` antes de pedir ao servidor              |
| Paginação "carregar mais"  | `loadingMore` + `PAGE_SIZE = 20` (`/brain`)                            |
| Categorias com *chips* coloridos | `/brain` (tabela §4)                                            |
| Compatibilidade com arrays antigos | `/brain` aceita resposta como array **ou** `{items,total,...}` |
| Erros amigáveis            | UI de erro com ações de repetir e selo de fiabilidade do modelo        |
| Guia integrado             | `/tutoriais` — cartões numerados com títulos e descrições curtos       |

## 7. Acessibilidade

- Contraste AA em todas as combinações (testar claro **e** escuro).
- `aria-label` nos ícones e SVGs (o `favicon.svg` já usa `aria-label="TugaAI"`).
- Foco visível, navegação por teclado e ordem de leitura lógica nos formulários de autenticação.
- `document.documentElement.lang` é atualizado dinamicamente pelo i18n (`lang` do locale ativo).
- Movimento: respeitar `prefers-reduced-motion` (transições de `src/lib/utils/transitions`).

## 8. Áudio e multimédia

- Sons: `static/audio/greeting.mp3` (saudação) e `static/audio/notification.mp3` (notificação).
- Voz/TTS: `kokoro-js` corre em worker dedicado (`src/lib/workers/KokoroWorker.ts`).
- Imagens: `static/image-placeholder.png`, `demo.png`, `banner.png` (213 965 B, raiz).

## 9. Checklist de revisão de UI

- [ ] Texto 100 % em PT-PT, sem *strings* em duro.
- [ ] Funciona em modo claro e escuro.
- [ ] Testado em telemóvel (375 px) e desktop.
- [ ] Estados de carga, vazio e erro desenhados (não só o estado de sucesso).
- [ ] Sem regressões no registo do service worker PWA.
- [ ] Atribuição ao Open WebUI preservada onde o texto é público.
