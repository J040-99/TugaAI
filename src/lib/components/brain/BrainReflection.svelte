<script lang="ts">
	import { getContext } from 'svelte';
	import dayjs from '$lib/dayjs';
	import { CATEGORY_STYLES } from './constants';

	const i18n = getContext('i18n');

	/** Último estado da reflexão periódica (GET /files/brain/state). */
	export let reflection: any = null;
</script>

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
				<div class="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-sm text-gray-600 dark:text-gray-300">
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
