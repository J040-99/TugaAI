<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import dayjs from '$lib/dayjs';

	import { WEBUI_BASE_URL } from '$lib/constants';

	import Spinner from '$lib/components/common/Spinner.svelte';

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
	let query = '';
	let category = 'all';
	let selectedEntity = '';

	const authHeaders = () => ({ Authorization: `Bearer ${localStorage.token}` });

	const load = async () => {
		loading = true;
		try {
			const [cardsRes, stateRes] = await Promise.all([
				fetch(`${WEBUI_BASE_URL}/api/v1/files/brain`, {
					headers: authHeaders(),
					credentials: 'include'
				}),
				fetch(`${WEBUI_BASE_URL}/api/v1/files/brain/state`, {
					headers: authHeaders(),
					credentials: 'include'
				})
			]);
			cards = cardsRes.ok ? await cardsRes.json() : [];
			reflection = stateRes.ok ? await stateRes.json() : null;
		} catch {
			cards = [];
			reflection = null;
		} finally {
			loading = false;
		}
	};

	onMount(load);

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
		documents: cards.length,
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
			{#if reflection?.memory_index || (reflection?.insights ?? []).length > 0}
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
				</section>
			{/if}

			<!-- Pesquisa + categorias -->
			<div class="mb-4 space-y-3">
				<input
					type="search"
					bind:value={query}
					placeholder={$i18n.t('Search memories...')}
					class="focus-ring w-full rounded-xl border border-gray-200 bg-white px-3.5 py-2 text-sm text-gray-900 outline-hidden placeholder:text-gray-400 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100"
				/>

				<div class="flex flex-wrap gap-1.5">
					<button
						class="rounded-full px-2.5 py-1 text-xs font-medium transition {category === 'all'
							? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900'
							: 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'}"
						on:click={() => (category = 'all')}
					>
						{$i18n.t('All')}
					</button>
					{#each CATEGORIES as cat (cat)}
						<button
							class="rounded-full px-2.5 py-1 text-xs font-medium transition {category === cat
								? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900'
								: 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'}"
							on:click={() => (category = cat)}
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
			{/if}
		</div>
	</div>
</div>
