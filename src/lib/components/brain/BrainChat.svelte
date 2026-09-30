<script lang="ts">
	import { getContext, onMount, onDestroy } from 'svelte';
	import { WEBUI_BASE_URL } from '$lib/constants';
	import { toast } from 'svelte-sonner';
	import Markdown from '$lib/components/chat/Messages/Markdown.svelte';

	const i18n = getContext('i18n');

	const authHeaders = () => ({ Authorization: `Bearer ${localStorage.token}` });

	// Histórico no SERVIDOR (GET/PUT/DELETE /files/brain/chat). O localStorage
	// fica apenas como espelho offline/migração de versões antigas.
	const CHAT_KEY = 'tugaai.brain.chat.v1';
	const REMOTE = `${WEBUI_BASE_URL}/api/v1/files/brain/chat`;

	let question = '';
	let asking = false;
	let askStartedAt = 0;
	let elapsed = 0;
	let ticker: ReturnType<typeof setInterval> | undefined;
	let chat: { q: string; a: string; sources: string[] }[] = [];

	const saveLocalMirror = () => {
		try {
			localStorage.setItem(CHAT_KEY, JSON.stringify(chat.slice(0, 50)));
		} catch {
			/* armazenamento indisponível */
		}
	};

	// Devolve true se o servidor guardou; caso contrário mantém o espelho local.
	const persistRemote = async (): Promise<boolean> => {
		try {
			const res = await fetch(REMOTE, {
				method: 'PUT',
				headers: { ...authHeaders(), 'Content-Type': 'application/json' },
				credentials: 'include',
				body: JSON.stringify({ items: chat.slice(0, 50) })
			});
			if (res.ok) {
				try {
					localStorage.removeItem(CHAT_KEY);
				} catch {
					/* noop */
				}
				return true;
			}
		} catch {
			/* servidor inacessível — fica o espelho */
		}
		saveLocalMirror();
		return false;
	};

	const restoreChat = async () => {
		let items: unknown[] = [];
		try {
			const res = await fetch(REMOTE, { headers: authHeaders(), credentials: 'include' });
			if (res.ok) {
				const data = await res.json();
				if (Array.isArray(data?.items)) items = data.items;
			}
		} catch {
			/* offline — tenta o espelho */
		}

		if (items.length === 0) {
			// Espelho local: histórico antigo ou servidor indisponível.
			try {
				const saved = JSON.parse(localStorage.getItem(CHAT_KEY) ?? '[]');
				if (Array.isArray(saved) && saved.length > 0) items = saved;
			} catch {
				/* sem espelho */
			}
			if (items.length > 0) {
				chat = items as typeof chat;
				await persistRemote(); // migra para o servidor de uma vez
				return;
			}
		}
		chat = items as typeof chat;
	};

	const clearChat = async () => {
		chat = [];
		try {
			localStorage.removeItem(CHAT_KEY);
		} catch {
			/* noop */
		}
		try {
			await fetch(REMOTE, { method: 'DELETE', headers: authHeaders(), credentials: 'include' });
		} catch {
			/* servidor inacessível — já limpamos o espelho */
		}
	};

	const askBrain = async () => {
		const q = question.trim();
		if (!q || asking) return;
		asking = true;
		askStartedAt = Date.now();
		elapsed = 0;
		try {
			const res = await fetch(`${WEBUI_BASE_URL}/api/v1/files/brain/ask`, {
				method: 'POST',
				headers: { ...authHeaders(), 'Content-Type': 'application/json' },
				credentials: 'include',
				body: JSON.stringify({ question: q })
			});
			if (!res.ok) throw new Error('ask failed');
			const data = await res.json();
			chat = [{ q, a: data.answer ?? '', sources: data.sources ?? [] }, ...chat];
			await persistRemote();
			question = '';
		} catch {
			toast.error($i18n.t('Uh-oh! There was an issue with the response.'));
		} finally {
			asking = false;
		}
	};

	onMount(() => {
		restoreChat();
		ticker = setInterval(() => {
			if (asking) elapsed = Math.floor((Date.now() - askStartedAt) / 1000);
		}, 1000);
	});

	onDestroy(() => {
		if (ticker) clearInterval(ticker);
	});
</script>

<section
	class="mb-6 rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
>
	<div class="flex items-center justify-between gap-2">
		<h2 class="text-sm font-semibold text-gray-900 dark:text-white">
			{$i18n.t('Talk to the brain')}
		</h2>
		{#if chat.length > 0}
			<button
				class="rounded-lg px-2 py-1 text-xs text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300"
				on:click={clearChat}
			>
				{$i18n.t('Clear conversation')}
			</button>
		{/if}
	</div>

	<!-- Aviso de velocidade: modelos gratuitos de raciocínio (20–60 s) -->
	<p class="mt-1 text-xs text-gray-400 dark:text-gray-500">
		{$i18n.t(
			'Free reasoning models take 20–60 s to answer — the bar means it is thinking, not stuck.'
		)}
	</p>

	<form class="mt-2 flex gap-2" on:submit|preventDefault={askBrain}>
		<input
			bind:value={question}
			disabled={asking}
			placeholder={$i18n.t('Ask anything about your knowledge...')}
			class="focus-ring min-w-0 flex-1 rounded-xl border border-gray-200 bg-white px-3.5 py-2 text-sm text-gray-900 outline-hidden placeholder:text-gray-400 disabled:opacity-60 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-100"
		/>
		<button
			type="submit"
			class="shrink-0 rounded-xl bg-gray-900 px-3.5 py-1.5 text-sm font-medium text-white transition hover:bg-gray-800 disabled:opacity-60 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
			disabled={asking || !question.trim()}
		>
			{asking ? '…' : $i18n.t('Send')}
		</button>
	</form>

	<!-- Barra de carregamento enquanto o cérebro raciocina -->
	{#if asking}
		<p class="mt-2 text-xs text-gray-400 dark:text-gray-500">
			{$i18n.t('Thinking…')}{elapsed > 0 ? ` (${elapsed}s)` : ''}
		</p>
		<div
			class="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800"
			role="progressbar"
		>
			<div
				class="brain-bar-indeterminate h-full w-2/5 rounded-full bg-gray-900 dark:bg-white"
			></div>
		</div>
	{/if}

	{#if chat.length > 0}
		<div class="mt-3 space-y-3">
			{#each chat as item (item.q + item.a.slice(0, 24))}
				<div class="rounded-xl bg-gray-50 p-3 dark:bg-gray-800/60">
					<div class="text-xs font-semibold text-gray-500 dark:text-gray-400">
						{item.q}
					</div>
					<div class="mt-1 text-sm text-gray-700 dark:text-gray-200">
						<Markdown content={item.a} />
					</div>
					{#if item.sources.length > 0}
						<div class="mt-1.5 text-xs text-gray-400 dark:text-gray-500">
							{$i18n.t('Sources')}: {item.sources.join(' · ')}
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</section>

<style>
	/* Barra indeterminada: desliza continuamente da esquerda para a direita —
	   o simple pulse dava a sensação de "parado" e parecia um erro. */
	@keyframes brain-bar-slide {
		0% {
			transform: translateX(-110%);
		}
		100% {
			transform: translateX(280%);
		}
	}

	.brain-bar-indeterminate {
		animation: brain-bar-slide 1.3s ease-in-out infinite;
		will-change: transform;
	}
</style>
