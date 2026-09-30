<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import dayjs from '$lib/dayjs';

	import { WEBUI_BASE_URL } from '$lib/constants';
	import BrainChat from '$lib/components/brain/BrainChat.svelte';
	import BrainManager from '$lib/components/brain/BrainManager.svelte';
	import BrainModels from '$lib/components/brain/BrainModels.svelte';
	import BrainReflection from '$lib/components/brain/BrainReflection.svelte';
	import BrainTimeline from '$lib/components/brain/BrainTimeline.svelte';
	import { CATEGORIES, ENTITY_STYLES } from '$lib/components/brain/constants';

	const i18n = getContext('i18n');

	let loading = true;
	let cards: any[] = [];
	let reflection: any = null;
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

	// Duplicados: cópias byte-a-byte idênticas (mesmo hash) entre os cartões carregados
	$: dupCounts = (() => {
		const map = new Map<string, number>();
		for (const card of cards) {
			const key = card.hash ?? card.id;
			map.set(key, (map.get(key) ?? 0) + 1);
		}
		return map;
	})();

	onMount(() => {
		loadPage(1, false);
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
			<BrainReflection {reflection} />

			<!-- Chat com o cérebro (histórico guardado no servidor) -->
			<BrainChat />

			<!-- Gestor de informação: adicionar, editar, reorganizar, apagar -->
			<BrainManager {cards} {dupCounts} onChanged={() => loadPage(1, false)} />

			<!-- Modelos por função — escolha deste cliente -->
			<BrainModels />

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

			<BrainTimeline
				{timeline}
				{loading}
				{loadingMore}
				{total}
				cardsCount={cards.length}
				emptyFiltered={filtered.length === 0}
				onEntity={toggleEntity}
				onTag={toggleTag}
				onLoadMore={loadMore}
			/>
		</div>
	</div>
</div>
