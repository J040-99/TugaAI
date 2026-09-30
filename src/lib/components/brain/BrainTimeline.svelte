<script lang="ts">
	import { getContext } from 'svelte';
	import dayjs from '$lib/dayjs';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import { CATEGORY_STYLES, ENTITY_STYLES } from './constants';

	const i18n = getContext('i18n');

	/** Grupos mensais prontos a mostrar (calculados pela página). */
	export let timeline: { label: string; items: any[] }[] = [];
	export let loading = true;
	export let loadingMore = false;
	export let total = 0;
	export let cardsCount = 0;
	export let emptyFiltered = false;

	export let onEntity: (name: string) => void = () => {};
	export let onTag: (tag: string) => void = () => {};
	export let onLoadMore: () => void = () => {};
</script>

{#if loading}
	<div class="flex justify-center py-16">
		<Spinner />
	</div>
{:else if cardsCount === 0}
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
{:else if emptyFiltered}
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
										on:click={() => onEntity(entity.name)}
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
										on:click={() => onTag(tag)}
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
	{#if cardsCount < total}
		<div class="mt-6 flex justify-center">
			<button
				class="rounded-xl border border-gray-200 px-4 py-2 text-sm text-gray-600 transition hover:bg-gray-50 disabled:opacity-60 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
				disabled={loadingMore}
				on:click={onLoadMore}
			>
				{loadingMore ? '…' : `${$i18n.t('Load more')} (${cardsCount}/${total})`}
			</button>
		</div>
	{/if}
{/if}
