<script lang="ts">
	import { getContext, onMount, onDestroy } from 'svelte';
	import dayjs from '$lib/dayjs';

	import { WEBUI_BASE_URL } from '$lib/constants';
	import { models } from '$lib/stores';
	import { getUserSettings, updateUserSettings } from '$lib/apis/users';
	import { toast } from 'svelte-sonner';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import Markdown from '$lib/components/chat/Messages/Markdown.svelte';

	const i18n = getContext('i18n');

	const CATEGORIES = ['memory', 'person', 'place', 'document', 'other'];

	const CATEGORY_STYLES: Record<string, string> = {
		memory: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
		person: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300',
		place: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
		document: 'bg-gray-100 text-gray-700 dark:bg-gray-500/15 dark:text-gray-300',
		other: 'bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300'
	};

	const ENTITY_STYLES: Record<string, string> = {
		person: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300',
		place: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
		topic: 'bg-gray-100 text-gray-700 dark:bg-gray-500/15 dark:text-gray-300'
	};

	let loading = true;
	let cards: any[] = [];
	let reflection: any = null;
	let organizeModel = '';
	let visionModel = '';
	let savingModels = false;
	let query = '';
	let category = 'all';
	let selectedEntity = '';

	const authHeaders = () => ({ Authorization: `Bearer ${localStorage.token}` });

	const PAGE_SIZE = 20;
	let page = 1;
	let total = 0;
	let loadingMore = false;
	let searchTimer: ReturnType<typeof setTimeout> | undefined;

	// O servidor é que filtra e pagina (JSON extract na BD) — o browser só
	// recebe a página pedida, nunca o volume todo.
	const loadPage = async (nextPage = 1, append = false) => {
		if (append) loadingMore = true;
		else loading = true;

		try {
			const params = new URLSearchParams({
				page: String(nextPage),
				limit: String(PAGE_SIZE)
			});
			if (query.trim()) params.set('q', query.trim());
			if (category && category !== 'all') params.set('category', category);

			const cardsRes = await fetch(`${WEBUI_BASE_URL}/api/v1/files/brain?${params}`, {
				headers: authHeaders(),
				credentials: 'include'
			});
			const payload = cardsRes.ok ? await cardsRes.json() : null;
			const items = Array.isArray(payload) ? payload : (payload?.items ?? []);

			cards = append ? [...cards, ...items] : items;
			total = Array.isArray(payload) ? items.length : (payload?.total ?? items.length);
			page = nextPage;

			if (!append && reflection === null) {
				const stateRes = await fetch(`${WEBUI_BASE_URL}/api/v1/files/brain/state`, {
					headers: authHeaders(),
					credentials: 'include'
				});
				reflection = stateRes.ok ? await stateRes.json() : null;
			}
		} catch {
			if (!append) {
				cards = [];
				reflection = null;
			}
		} finally {
			loading = false;
			loadingMore = false;
		}
	};

	const scheduleSearch = () => {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(() => loadPage(1, false), 300);
	};

	const loadMore = () => loadPage(page + 1, true);

	// Chat com o cérebro: pergunta → /brain/ask → resposta com fontes.
	const CHAT_KEY = 'tugaai.brain.chat.v1';
	let question = '';
	let asking = false;
	let askStartedAt = 0;
	let elapsed = 0;
	let ticker: ReturnType<typeof setInterval> | undefined;
	let chat: { q: string; a: string; sources: string[] }[] = [];

	// Gestor de informação (ficheiros do cérebro)
	let uploading = false;
	let fileInput: HTMLInputElement;
	let editingId = '';
	let editTitle = '';
	let editSummary = '';

	const persistChat = () => {
		try {
			localStorage.setItem(CHAT_KEY, JSON.stringify(chat.slice(0, 50)));
		} catch {
			/* armazenamento indisponível */
		}
	};

	const restoreChat = () => {
		try {
			const saved = JSON.parse(localStorage.getItem(CHAT_KEY) ?? '[]');
			if (Array.isArray(saved)) chat = saved;
		} catch {
			chat = [];
		}
	};

	const clearChat = () => {
		chat = [];
		try {
			localStorage.removeItem(CHAT_KEY);
		} catch {
			/* noop */
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
			persistChat();
			question = '';
		} catch {
			toast.error($i18n.t('Uh-oh! There was an issue with the response.'));
		} finally {
			asking = false;
		}
	};

	const onUploadFiles = async (event: Event) => {
		const input = event.target as HTMLInputElement;
		if (!input.files || input.files.length === 0) return;
		uploading = true;
		try {
			for (const file of Array.from(input.files)) {
				const form = new FormData();
				form.append('file', file);
				const res = await fetch(`${WEBUI_BASE_URL}/api/v1/files/?process=true`, {
					method: 'POST',
					headers: authHeaders(),
					credentials: 'include',
					body: form
				});
				if (!res.ok) throw new Error('upload failed');
			}
			toast.success($i18n.t('Uploaded'));
			await loadPage(1, false);
		} catch {
			toast.error($i18n.t('Uh-oh! There was an issue with the response.'));
		} finally {
			uploading = false;
			input.value = '';
		}
	};

	const deleteFile = async (id: string, name: string) => {
		if (!confirm(`${$i18n.t('Delete')}: ${name}`)) return;
		try {
			const res = await fetch(`${WEBUI_BASE_URL}/api/v1/files/${id}`, {
				method: 'DELETE',
				headers: authHeaders(),
				credentials: 'include'
			});
			if (!res.ok) throw new Error('delete failed');
			toast.success($i18n.t('Deleted'));
			await loadPage(1, false);
		} catch {
			toast.error($i18n.t('Uh-oh! There was an issue with the response.'));
		}
	};

	const reorganiseFile = async (id: string) => {
		try {
			const res = await fetch(`${WEBUI_BASE_URL}/api/v1/files/brain/${id}/reorganize`, {
				method: 'POST',
				headers: authHeaders(),
				credentials: 'include'
			});
			if (!res.ok) throw new Error('reorganize failed');
			toast.success($i18n.t('Saved'));
			await loadPage(1, false);
		} catch {
			toast.error($i18n.t('Uh-oh! There was an issue with the response.'));
		}
	};

	const startEditCard = (card: any) => {
		editingId = card.id;
		editTitle = card.brain?.title ?? '';
		editSummary = card.brain?.summary ?? '';
	};

	const saveCard = async (id: string) => {
		try {
			const res = await fetch(`${WEBUI_BASE_URL}/api/v1/files/brain/${id}/card`, {
				method: 'PUT',
				headers: { ...authHeaders(), 'Content-Type': 'application/json' },
				credentials: 'include',
				body: JSON.stringify({ title: editTitle, summary: editSummary })
			});
			if (!res.ok) throw new Error('save failed');
			toast.success($i18n.t('Saved'));
			editingId = '';
			await loadPage(1, false);
		} catch {
			toast.error($i18n.t('Uh-oh! There was an issue with the response.'));
		}
	};

	// Preferências deste cliente: que modelo o cérebro usa em cada função.
	const loadBrainSettings = async () => {
		try {
			const settings = await getUserSettings(localStorage.token);
			const brain = settings?.brain ?? {};
			organizeModel = brain.organize_model ?? '';
			visionModel = brain.vision_model ?? '';
		} catch {
			/* sem preferências guardadas — fica o default do servidor */
		}
	};

	const saveBrainSettings = async () => {
		savingModels = true;
		try {
			const current = (await getUserSettings(localStorage.token)) ?? {};
			await updateUserSettings(localStorage.token, {
				...current,
				brain: {
					...(current.brain ?? {}),
					organize_model: organizeModel,
					vision_model: visionModel
				}
			});
			toast.success($i18n.t('Saved'));
		} catch {
			toast.error($i18n.t('Uh-oh! There was an issue with the response.'));
		} finally {
			savingModels = false;
		}
	};

	onMount(() => {
		restoreChat();
		loadPage(1, false);
		loadBrainSettings();
		ticker = setInterval(() => {
			if (asking) elapsed = Math.floor((Date.now() - askStartedAt) / 1000);
		}, 1000);
	});

	onDestroy(() => {
		if (ticker) clearInterval(ticker);
	});

	$: filtered = cards.filter((card) => {
		const brain = card?.brain ?? {};
		if (category !== 'all' && brain.category !== category) return false;
		if (selectedEntity && !(brain.entities ?? []).some((e: any) => e.name === selectedEntity)) {
			return false;
		}
		if (!query.trim()) return true;
		const haystack = [
			brain.title,
			brain.summary,
			card?.filename,
			...(brain.tags ?? []),
			...(brain.entities ?? []).map((e: any) => e.name)
		]
			.filter(Boolean)
			.join(' ')
			.toLowerCase();
		return haystack.includes(query.trim().toLowerCase());
	});

	$: entityIndex = (() => {
		const map = new Map<string, { name: string; type: string; count: number }>();
		for (const card of cards) {
			for (const entity of card?.brain?.entities ?? []) {
				const current = map.get(entity.name) ?? {
					name: entity.name,
					type: entity.type,
					count: 0
				};
				current.count += 1;
				map.set(entity.name, current);
			}
		}
		return [...map.values()].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
	})();

	$: tagIndex = (() => {
		const map = new Map<string, number>();
		for (const card of cards) {
			for (const tag of card?.brain?.tags ?? []) {
				map.set(tag, (map.get(tag) ?? 0) + 1);
			}
		}
		return [...map.entries()]
			.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
			.slice(0, 24)
			.map(([name, count]) => ({ name, count }));
	})();

	$: stats = {
		documents: total || cards.length,
		people: entityIndex.filter((e) => e.type === 'person').length,
		places: entityIndex.filter((e) => e.type === 'place').length,
		tags: tagIndex.length
	};

	const dateOf = (card: any): string | null => {
		const brain = card?.brain ?? {};
		if (brain.date) return brain.date;
		if (card?.created_at) return dayjs(card.created_at * 1000).format('YYYY-MM-DD');
		return null;
	};

	const groupLabel = (date: string | null): string => {
		if (!date) return $i18n.t('Undated');
		return dayjs(date).format('MMMM YYYY');
	};

	// Agrupa por mês para a cronologia.
	$: timeline = (() => {
		const groups: { label: string; items: any[] }[] = [];
		for (const card of filtered) {
			const date = dateOf(card);
			const label = groupLabel(date);
			const last = groups[groups.length - 1];
			if (last && last.label === label) {
				last.items.push(card);
			} else {
				groups.push({ label, items: [card] });
			}
		}
		return groups;
	})();

	const toggleEntity = (name: string) => {
		selectedEntity = selectedEntity === name ? '' : name;
	};

	const toggleTag = (tag: string) => {
		query = query === tag ? '' : tag;
		scheduleSearch();
	};
</script>

<svelte:head>
	<title>{$i18n.t('Brain')}</title>
</svelte:head>

<div class="flex h-full w-full flex-col overflow-x-hidden">
	<div class="flex-1 overflow-y-auto">
		<div class="mx-auto w-full max-w-4xl px-4 pt-6 pb-24 sm:px-6">
			<header class="mb-6">
				<h1 class="text-xl font-semibold text-gray-900 dark:text-white">
					{$i18n.t('Brain')}
				</h1>
				<p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
					{$i18n.t('Your knowledge, organised')}
				</p>

				<div class="mt-4 flex flex-wrap gap-4 text-sm text-gray-600 dark:text-gray-300">
					<span><strong>{stats.documents}</strong> {$i18n.t('documents')}</span>
					<span><strong>{stats.people}</strong> {$i18n.t('people')}</span>
					<span><strong>{stats.places}</strong> {$i18n.t('places')}</span>
					<span><strong>{stats.tags}</strong> {$i18n.t('tags')}</span>
				</div>
			</header>

			<!-- Reflexão periódica: o que o cérebro "pensou" na última revisão -->
			{#if reflection?.memory_index || (reflection?.insights ?? []).length > 0 || (reflection?.stats?.documents ?? 0) > 0}
				<section
					class="mb-6 rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
				>
					<div class="flex items-center justify-between gap-3">
						<h2 class="text-sm font-semibold text-gray-900 dark:text-white">
							{$i18n.t('Reflection')}
						</h2>
						{#if reflection?.updated_at}
							<span class="shrink-0 text-xs text-gray-400 dark:text-gray-500">
								{$i18n.t('Last reflection')}
								{dayjs(reflection.updated_at * 1000).fromNow()}
							</span>
						{/if}
					</div>

					{#if reflection?.memory_index}
						<p class="mt-2 text-sm leading-6 text-gray-600 dark:text-gray-300">
							{reflection.memory_index}
						</p>
					{/if}

					{#if (reflection?.insights ?? []).length > 0}
						<div class="mt-3 space-y-2">
							{#each reflection.insights as insight (insight.topic)}
								<div class="rounded-xl bg-gray-50 p-3 dark:bg-gray-800/60">
									<div class="text-xs font-semibold text-gray-800 dark:text-gray-100">
										{insight.topic}
									</div>
									<p class="mt-1 text-sm text-gray-600 dark:text-gray-300">
										{insight.summary}
									</p>
									{#if insight.related?.length > 0}
										<div class="mt-1.5 flex flex-wrap gap-1.5">
											{#each insight.related as title (title)}
												<span
													class="rounded-md bg-gray-200/70 px-1.5 py-0.5 text-[0.6875rem] text-gray-600 dark:bg-gray-700/70 dark:text-gray-300"
												>
													{title}
												</span>
											{/each}
										</div>
									{/if}
								</div>
							{/each}
						</div>
					{/if}
					<!-- Estatísticas: o cérebro calcula com TODOS os ficheiros,
					     não só com a página carregada (escala) -->
					{#if (reflection?.stats?.documents ?? 0) > 0}
						<div class="mt-3 border-t border-gray-100 pt-3 dark:border-gray-800">
							<div class="text-xs font-medium uppercase tracking-wide text-gray-400">
								{$i18n.t('Brain statistics')}
							</div>
							<div
								class="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-sm text-gray-600 dark:text-gray-300"
							>
								<span
									><strong>{reflection.stats.documents}</strong>
									{$i18n.t('documents')}</span
								>
								<span><strong>{reflection.stats.people}</strong> {$i18n.t('people')}</span>
								<span><strong>{reflection.stats.places}</strong> {$i18n.t('places')}</span>
								<span><strong>{reflection.stats.tags}</strong> {$i18n.t('tags')}</span>
							</div>

							{#if Object.keys(reflection.stats.categories ?? {}).length > 0}
								<div class="mt-2 flex flex-wrap gap-1.5">
									{#each Object.entries(reflection.stats.categories) as [cat, count] (cat)}
										<span
											class="rounded-full px-2 py-0.5 text-xs font-medium {CATEGORY_STYLES[cat] ??
												CATEGORY_STYLES.other}"
										>
											{$i18n.t(cat)} · {count}
										</span>
									{/each}
								</div>
							{/if}

							{#if (reflection.stats.top_entities ?? []).length > 0}
								<div class="mt-2 flex flex-wrap gap-1.5 text-xs text-gray-500">
									{#each reflection.stats.top_entities.slice(0, 10) as entity (`${entity.type}-${entity.name}`)}
										<span class="rounded-md bg-gray-100 px-1.5 py-0.5 dark:bg-gray-800">
											{entity.name} · {entity.count}
										</span>
									{/each}
								</div>
							{/if}
						</div>
					{/if}
				</section>
			{/if}

			<!-- Chat com o cérebro -->
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

			<!-- Gestor de informação: adicionar, editar, reorganizar, apagar -->
			<section
				class="mb-6 rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
			>
				<div class="flex items-center justify-between gap-3">
					<h2 class="text-sm font-semibold text-gray-900 dark:text-white">
						{$i18n.t('Information manager')}
					</h2>
					<button
						class="rounded-xl bg-gray-900 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-gray-800 disabled:opacity-60 dark:bg-white dark:text-gray-900"
						disabled={uploading}
						on:click={() => fileInput?.click()}
					>
						{uploading ? '…' : `+ ${$i18n.t('Add Files')}`}
					</button>
					<input
						bind:this={fileInput}
						type="file"
						multiple
						class="hidden"
						on:change={onUploadFiles}
					/>
				</div>

				<div class="mt-3 space-y-2">
					{#each cards as card (card.id)}
						<div class="rounded-xl border border-gray-100 p-2.5 dark:border-gray-800">
							<div class="flex flex-wrap items-center gap-2">
								<span class="min-w-0 flex-1 truncate text-sm text-gray-800 dark:text-gray-100">
									{card.filename}
								</span>
								<button
									class="rounded-lg bg-gray-100 px-2 py-1 text-xs text-gray-600 transition hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
									on:click={() => reorganiseFile(card.id)}
								>
									{$i18n.t('Reorganise')}
								</button>
								<button
									class="rounded-lg bg-gray-100 px-2 py-1 text-xs text-gray-600 transition hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
									on:click={() => startEditCard(card)}
								>
									{$i18n.t('Edit')}
								</button>
								<button
									class="rounded-lg bg-red-50 px-2 py-1 text-xs text-red-600 transition hover:bg-red-100 dark:bg-red-500/10 dark:text-red-400"
									on:click={() => deleteFile(card.id, card.filename)}
								>
									{$i18n.t('Delete')}
								</button>
							</div>

							{#if editingId === card.id}
								<div class="mt-2 space-y-2">
									<input
										bind:value={editTitle}
										class="focus-ring w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-950"
										placeholder={$i18n.t('Title')}
									/>
									<textarea
										bind:value={editSummary}
										rows="2"
										class="focus-ring w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-950"
										placeholder={$i18n.t('Summary')}
									></textarea>
									<div class="flex gap-2">
										<button
											class="rounded-lg bg-gray-900 px-2.5 py-1 text-xs font-medium text-white disabled:opacity-60 dark:bg-white dark:text-gray-900"
											on:click={() => saveCard(card.id)}
										>
											{$i18n.t('Save')}
										</button>
										<button
											class="rounded-lg bg-gray-100 px-2.5 py-1 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-300"
											on:click={() => (editingId = '')}
										>
											{$i18n.t('Cancel')}
										</button>
									</div>
								</div>
							{/if}
						</div>
					{/each}

					{#if cards.length === 0}
						<p class="text-xs text-gray-400 dark:text-gray-500">
							{$i18n.t('No memories yet')}
						</p>
					{/if}
				</div>
			</section>

			<!-- Modelos por função — escolha deste cliente -->
			<section
				class="mb-6 rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
			>
				<h2 class="text-sm font-semibold text-gray-900 dark:text-white">
					{$i18n.t('Brain models')}
				</h2>
				<p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
					{$i18n.t('Choose which model the brain uses for each task.')}
				</p>

				<div class="mt-3 grid gap-3 sm:grid-cols-2">
					<label class="block text-xs text-gray-500 dark:text-gray-400">
						{$i18n.t('File organisation')}
						<select
							bind:value={organizeModel}
							class="focus-ring mt-1 w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 outline-hidden dark:border-gray-800 dark:bg-gray-950 dark:text-gray-100"
						>
							<option value="">{$i18n.t('Server default')}</option>
							{#each $models as m (m.id)}
								<option value={m.id}>{m.id}</option>
							{/each}
						</select>
					</label>

					<label class="block text-xs text-gray-500 dark:text-gray-400">
						{$i18n.t('Images and PDFs')}
						<select
							bind:value={visionModel}
							class="focus-ring mt-1 w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 outline-hidden dark:border-gray-800 dark:bg-gray-950 dark:text-gray-100"
						>
							<option value="">{$i18n.t('Server default')}</option>
							{#each $models as m (m.id)}
								<option value={m.id}>{m.id}</option>
							{/each}
						</select>
					</label>
				</div>

				<div class="mt-3 flex flex-wrap items-center gap-3">
					<button
						class="rounded-xl bg-gray-900 px-3.5 py-1.5 text-sm font-medium text-white transition hover:bg-gray-800 disabled:opacity-60 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
						disabled={savingModels}
						on:click={saveBrainSettings}
					>
						{$i18n.t('Save')}
					</button>
					<span class="text-xs text-gray-400 dark:text-gray-500">
						{$i18n.t('Reflection uses the server default model.')}
					</span>
				</div>
			</section>

			<!-- Pesquisa + categorias -->
			<div class="mb-4 space-y-3">
				<input
					type="search"
					bind:value={query}
					on:input={scheduleSearch}
					placeholder={$i18n.t('Search memories...')}
					class="focus-ring w-full rounded-xl border border-gray-200 bg-white px-3.5 py-2 text-sm text-gray-900 outline-hidden placeholder:text-gray-400 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100"
				/>

				<div class="flex flex-wrap gap-1.5">
					<button
						class="rounded-full px-2.5 py-1 text-xs font-medium transition {category === 'all'
							? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900'
							: 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'}"
						on:click={() => {
							category = 'all';
							loadPage(1, false);
						}}
					>
						{$i18n.t('All')}
					</button>
					{#each CATEGORIES as cat (cat)}
						<button
							class="rounded-full px-2.5 py-1 text-xs font-medium transition {category === cat
								? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900'
								: 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'}"
							on:click={() => {
								category = cat;
								loadPage(1, false);
							}}
						>
							{$i18n.t(cat)}
						</button>
					{/each}
				</div>
			</div>

			{#if entityIndex.length > 0}
				<div class="mb-3">
					<div class="mb-1.5 text-xs font-medium uppercase tracking-wide text-gray-400">
						{$i18n.t('Entities')}
					</div>
					<div class="flex flex-wrap gap-1.5">
						{#each entityIndex.slice(0, 14) as entity (entity.name)}
							<button
								class="rounded-full px-2 py-0.5 text-xs font-medium transition {selectedEntity ===
								entity.name
									? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900'
									: (ENTITY_STYLES[entity.type] ?? ENTITY_STYLES.topic)}"
								title="{entity.count}×"
								on:click={() => toggleEntity(entity.name)}
							>
								{entity.name}
								{#if entity.count > 1}<span class="opacity-60">·{entity.count}</span>{/if}
							</button>
						{/each}
					</div>
				</div>
			{/if}

			{#if tagIndex.length > 0}
				<div class="mb-5">
					<div class="mb-1.5 text-xs font-medium uppercase tracking-wide text-gray-400">
						{$i18n.t('Tags')}
					</div>
					<div class="flex flex-wrap gap-1.5">
						{#each tagIndex as tag (tag.name)}
							<button
								class="rounded-md bg-gray-100 px-2 py-0.5 text-xs text-gray-600 transition hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700 {query ===
								tag.name
									? '!bg-gray-900 !text-white dark:!bg-white dark:!text-gray-900'
									: ''}"
								on:click={() => toggleTag(tag.name)}
							>
								#{tag.name}
							</button>
						{/each}
					</div>
				</div>
			{/if}

			{#if loading}
				<div class="flex justify-center py-16">
					<Spinner />
				</div>
			{:else if cards.length === 0}
				<div
					class="rounded-2xl border border-dashed border-gray-200 px-6 py-14 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400"
				>
					<p class="font-medium text-gray-700 dark:text-gray-200">
						{$i18n.t('No memories yet')}
					</p>
					<p class="mt-1">
						{$i18n.t('Add files in Workspace → Knowledge and the brain will organise them here.')}
					</p>
				</div>
			{:else if filtered.length === 0}
				<div class="py-14 text-center text-sm text-gray-500 dark:text-gray-400">
					{$i18n.t('No results')}
				</div>
			{:else}
				<!-- Cronologia -->
				{#each timeline as group (group.label)}
					<div class="mb-6">
						<div class="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
							{group.label}
						</div>

						<div class="space-y-3">
							{#each group.items as card (card.id)}
								<article
									class="rounded-xl border border-gray-200 bg-white p-4 transition hover:border-gray-300 dark:border-gray-800 dark:bg-gray-900 dark:hover:border-gray-700"
								>
									<div class="flex items-start justify-between gap-3">
										<div class="min-w-0">
											<h2 class="truncate text-sm font-semibold text-gray-900 dark:text-white">
												{card.brain.title}
											</h2>
											{#if card.brain.summary}
												<p class="mt-1 text-sm text-gray-600 dark:text-gray-300">
													{card.brain.summary}
												</p>
											{/if}
										</div>

										<span
											class="shrink-0 rounded-full px-2 py-0.5 text-[0.6875rem] font-medium {CATEGORY_STYLES[
												card.brain.category
											] ?? CATEGORY_STYLES.other}"
										>
											{$i18n.t(card.brain.category)}
										</span>
									</div>

									{#if card.brain.entities.length > 0}
										<div class="mt-2 flex flex-wrap gap-1.5">
											{#each card.brain.entities as entity (`${entity.type}-${entity.name}`)}
												<button
													class="rounded-full px-2 py-0.5 text-xs {ENTITY_STYLES[entity.type] ??
														ENTITY_STYLES.topic}"
													on:click={() => toggleEntity(entity.name)}
												>
													{entity.name}
												</button>
											{/each}
										</div>
									{/if}

									<div
										class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-400 dark:text-gray-500"
									>
										{#if card.brain.date}
											<span class="tabular-nums">{card.brain.date}</span>
										{/if}
										<span class="truncate">{card.filename}</span>
										{#if card.brain.organized_at}
											<span class="ml-auto shrink-0">
												{$i18n.t('organised')}
												{dayjs(card.brain.organized_at * 1000).fromNow()}
											</span>
										{/if}
									</div>

									{#if card.brain.tags.length > 0}
										<div class="mt-2 flex flex-wrap gap-1.5">
											{#each card.brain.tags as tag (tag)}
												<button
													class="text-xs text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
													on:click={() => toggleTag(tag)}
												>
													#{tag}
												</button>
											{/each}
										</div>
									{/if}
								</article>
							{/each}
						</div>
					</div>
				{/each}
				{#if cards.length < total}
					<div class="mt-6 flex justify-center">
						<button
							class="rounded-xl border border-gray-200 px-4 py-2 text-sm text-gray-600 transition hover:bg-gray-50 disabled:opacity-60 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
							disabled={loadingMore}
							on:click={loadMore}
						>
							{loadingMore ? '…' : `${$i18n.t('Load more')} (${cards.length}/${total})`}
						</button>
					</div>
				{/if}
			{/if}
		</div>
	</div>
</div>

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
