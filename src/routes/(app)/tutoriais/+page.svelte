<script lang="ts">
	import {
		WEBUI_NAME,
		showSidebar,
		mobile,
		user,
		settings,
		showSettings
	} from '$lib/stores';
	import { goto } from '$app/navigation';
	import { getContext, onMount } from 'svelte';
	import QuestionMarkCircle from '$lib/components/icons/QuestionMarkCircle.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';

	const i18n = getContext('i18n');

	let loaded = false;
	let openId: string | null = 'openrouter';

	const tutorials = [
		{
			id: 'openrouter',
			title: '1. Criar conta e chave API no OpenRouter',
			description: 'O OpenRouter é o serviço que paga as mensagens de IA. A chave é sua — o TugaAI não guarda o seu saldo.',
			steps: [
				'Abra openrouter.ai no telemóvel ou computador e crie uma conta (pode usar Google ou e-mail).',
				'Em Credits (ou Settings → Credits), carregue saldo com cartão. Pode começar com pouco (ex.: 5 €) — o consumo é pago ao usar.',
				'Vá a Keys (openrouter.ai/keys) e clique em Create Key.',
				'Dê um nome fácil de reconhecer, ex.: "TugaAI".',
				'Copie a chave (começa por sk-or-...). Guarde-a bem — não a partilhe em público.',
				'No TugaAI: Definições → Ligações → + e cole a chave no passo 2 abaixo.'
			]
		},
		{
			id: 'ligar',
			title: '2. Ligar a chave no TugaAI',
			description: 'Uma vez ligada, os modelos OpenRouter aparecem no seletor de modelos e já pode conversar.',
			steps: [
				'No TugaAI, abra o menu do utilizador (canto inferior esquerdo / avatar) → Definições.',
				'A aba Ligações (Connections) → botão + em "Ligações diretas".',
				'URL: https://openrouter.ai/api/v1 (já vem pré-preenchida nas sugestões).',
				'Chave da API: cole a chave sk-or-... que copiou no OpenRouter.',
				'Clique no ícone de verificação (para testar) e depois Guardar.',
				'Volte ao chat. No seletor de modelos, escolha um modelo OpenRouter (ex.: modelos baratos para começar).',
				'Se não aparecerem modelos, carregue em Atualizar modelos ou faça logout/login uma vez.'
			]
		},
		{
			id: 'primeira-conversa',
			title: '3. Primeira conversa (telemóvel)',
			description: 'O fluxo básico para usar no dia a dia.',
			steps: [
				'Abra o TugaAI no browser do telemóvel (ou app instalada — ver tutorial 4).',
				'Toque em Novo chat (ícone de lápis) se ainda não tiver uma conversa aberta.',
				'Escolha o modelo no topo (ex.: um modelo "sonnet" ou "flash" para respostas rápidas e baratas).',
				'Escreva a pergunta e toque em enviar (seta).',
				'Para imagens ou ficheiros: use o + junto à caixa de texto (consoante o modelo).',
				'Para voltar às conversas antigas: menu lateral → lista de chats.'
			]
		},
		{
			id: 'telemovel',
			title: '4. Instalar no telemóvel (como app)',
			description: 'O TugaAI é uma PWA: pode instalar-se no ecrã inicial sem loja de aplicações.',
			steps: [
				'Android (Chrome): abra o site → menu ⋮ → "Adicionar ao ecrã inicial" / "Instalar app".',
				'iPhone (Safari): abra o site → botão Partilhar → "Adicionar ao Ecrã Início".',
				'Confirme o nome TugaAI e toque em Adicionar.',
				'Abre em ecrã inteiro, sem barra do browser — mais fácil de usar no dia a dia.'
			]
		},
		{
			id: 'custos',
			title: '5. Custos e dicas para poupar',
			description: 'A fatura é do OpenRouter, não do TugaAI. Estas dicas ajudam a controlar gastos.',
			steps: [
				'Comece por modelos baratos/fast para perguntas simples; use modelos maiores só quando precisar.',
				'No OpenRouter, defina um limite mensal em Credits para evitar surpresas.',
				'Conversas longas consomem mais: para tarefas pequenas, prefira chats curtos.',
				'Se a chave for roubada, revogue-a no OpenRouter e crie outra nova no TugaAI.',
				'No chat, escolha modelos com preço visível na lista do OpenRouter (coluna preço).'
			]
		},
		{
			id: 'faq',
			title: '6. Perguntas frequentes',
			description: 'Problemas comuns e solução rápida.',
			steps: [
				'"Sem modelos disponíveis" → ligue a chave no tutorial 2 e atualize a lista de modelos.',
				'"Erro 401 / unauthorized" → chave errada ou revogada; copie outra vez a chave sk-or-....',
				'"Erro 402 / insufficient credit" → carregue saldo no OpenRouter.',
				'"Ligação recusada/CORS" → confirme que a URL é https://openrouter.ai/api/v1.',
				'Esqueceu-se da chave? Não dá para ver no TugaAI — crie uma nova no OpenRouter (Keys) e substitua na Ligações.',
				'Precisa de ajuda com a conta TugaAI (password): contacte o administrador deste servidor.'
			]
		}
	];

	const toggle = (id: string) => {
		openId = openId === id ? null : id;
	};

	onMount(() => {
		loaded = true;
	});
</script>

<svelte:head>
	<title>{$i18n.t('Tutorials')} / {$WEBUI_NAME}</title>
</svelte:head>

{#if loaded}
	<div
		class="flex flex-col w-full h-screen max-h-[100dvh] transition-width duration-200 ease-in-out {$showSidebar
			? 'md:max-w-[calc(100%-var(--sidebar-width))]'
			: ''} max-w-full"
	>
		<div class="flex-1 max-h-full overflow-y-auto">
			<div class="mx-auto w-full max-w-2xl px-4 pt-4 pb-24 sm:px-6">
				<header class="mb-5">
					<button
						type="button"
						class="mb-3 inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white transition"
						on:click={() => goto('/')}
					>
						<span aria-hidden="true">←</span>
						{$i18n.t('New Chat')}
					</button>

					<div class="flex items-start gap-3">
						<div
							class="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-black text-white dark:bg-white dark:text-black"
						>
							<QuestionMarkCircle className="size-5" />
						</div>
						<div class="min-w-0">
						<h1 class="text-xl font-semibold tracking-tight text-gray-900 dark:text-white">
							{$i18n.t('Tutorials')}
						</h1>
						<p class="mt-1 text-sm leading-relaxed text-gray-500 dark:text-gray-400">
							{$i18n.t(
								'Quick guide to start using TugaAI on your phone: OpenRouter key, first chat and install as an app.'
							)}
						</p>
						</div>
					</div>
				</header>

				{#if !($settings?.directConnections?.OPENAI_API_KEYS?.some((k) => k)) && !($user?.role === 'admin')}
					<div
						class="mb-5 rounded-2xl border border-amber-200/80 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100"
					>
						<p class="font-medium">{$i18n.t('You have not connected your OpenRouter key yet.')}</p>
						<p class="mt-1 opacity-90">
							{$i18n.t('Follow steps 1 and 2 to enable AI models.')}
						</p>
					</div>
				{/if}

				<nav class="mb-4 flex flex-wrap gap-2" aria-label={$i18n.t('Tutorials')}>
					{#each tutorials as t (t.id)}
						<button
							type="button"
							class="rounded-full border px-3 py-1.5 text-xs transition {openId === t.id
								? 'border-black bg-black text-white dark:border-white dark:bg-white dark:text-black'
								: 'border-gray-200 text-gray-600 hover:border-gray-400 dark:border-gray-700 dark:text-gray-300 dark:hover:border-gray-500'}"
							on:click={() => {
								openId = t.id;
								document
									.getElementById(`tut-${t.id}`)
									?.scrollIntoView({ behavior: 'smooth', block: 'start' });
							}}
						>
							{t.title.split('.')[0]}.
						</button>
					{/each}
				</nav>

				<div class="space-y-3">
					{#each tutorials as t (t.id)}
						<section
							id="tut-{t.id}"
							class="scroll-mt-4 overflow-hidden rounded-2xl border border-gray-200/80 bg-white dark:border-gray-800 dark:bg-gray-900/60"
						>
							<button
								type="button"
								class="flex w-full items-start justify-between gap-3 px-4 py-3.5 text-left transition hover:bg-gray-50 dark:hover:bg-gray-800/50"
								aria-expanded={openId === t.id}
								on:click={() => toggle(t.id)}
							>
								<span class="min-w-0">
									<span class="block text-sm font-medium text-gray-900 dark:text-white">
										{t.title}
									</span>
									<span class="mt-0.5 block text-xs leading-relaxed text-gray-500 dark:text-gray-400">
										{t.description}
									</span>
								</span>
								<span
									class="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full text-gray-400 transition {openId === t.id
										? 'rotate-45 text-gray-900 dark:text-white'
										: ''}"
									aria-hidden="true"
								>
									<Plus className="size-4" />
								</span>
							</button>

							{#if openId === t.id}
								<div class="border-t border-gray-100 px-4 py-4 dark:border-gray-800">
									<ol class="space-y-3">
										{#each t.steps as step, i (i)}
											<li class="flex gap-3">
												<span
													class="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-gray-100 text-[0.6875rem] font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-300"
												>
													{i + 1}
												</span>
												<span class="text-sm leading-relaxed text-gray-700 dark:text-gray-300">
													{#if step.includes('https://openrouter.ai/api/v1')}
														{@html step.replace(
															/(https:\/\/openrouter\.ai\/api\/v1)/,
															'<code class="rounded bg-gray-100 px-1 py-0.5 text-xs dark:bg-gray-800">$1</code>'
														)}
													{:else if step.includes('sk-or-')}
														{@html step.replace(
															/(sk-or-\.\.\.)/,
															'<code class="rounded bg-gray-100 px-1 py-0.5 text-xs dark:bg-gray-800">$1</code>'
														)}
													{:else}
														{step}
													{/if}
												</span>
											</li>
										{/each}
									</ol>

									{#if t.id === 'openrouter' || t.id === 'ligar'}
										<div class="mt-4 flex flex-wrap gap-2">
											<a
												href="https://openrouter.ai/keys"
												target="_blank"
												rel="noopener noreferrer"
												class="inline-flex items-center justify-center rounded-full bg-black px-4 py-2 text-xs font-medium text-white transition hover:bg-gray-900 dark:bg-white dark:text-black dark:hover:bg-gray-100"
											>
												{$i18n.t('Open OpenRouter Keys')}
											</a>
											{#if t.id === 'ligar'}
												<button
													type="button"
													class="inline-flex items-center justify-center rounded-full border border-gray-200 px-4 py-2 text-xs font-medium text-gray-700 transition hover:border-gray-400 dark:border-gray-700 dark:text-gray-200 dark:hover:border-gray-500"
													on:click={async () => {
														await showSettings.set('connections');
														if ($mobile) {
															showSidebar.set(false);
														}
													}}
												>
													{$i18n.t('Open Connections')}
												</button>
											{/if}
										</div>
									{/if}

									{#if t.id === 'telemovel'}
										<p class="mt-4 text-xs text-gray-400 dark:text-gray-500">
											{$i18n.t('Installation works over HTTPS or localhost.')}
										</p>
									{/if}
								</div>
							{/if}
						</section>
					{/each}
				</div>

				<footer class="mt-8 border-t border-gray-100 pt-4 text-xs leading-relaxed text-gray-400 dark:border-gray-800 dark:text-gray-500">
					{$i18n.t(
						'TugaAI is made possible by the Open WebUI project (original license kept). AI calls are made through your OpenRouter key.'
					)}
				</footer>
			</div>
		</div>
	</div>
{/if}
