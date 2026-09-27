<script lang="ts">
	import { createEventDispatcher, getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	const i18n = getContext<Writable<i18nType>>('i18n');
	const dispatch = createEventDispatcher();

	export let icon: 'knowledge' | 'models' | 'prompts' | 'skills' | 'tools' = 'knowledge';
	export let title = '';
	export let description = '';
	export let hint = '';
	export let actionLabel = '';
	export let actionHref = '';
	export let secondaryLabel = '';
	export let secondaryHref = '';

	const glyphs: Record<string, string> = {
		knowledge: '📚',
		models: '🤖',
		prompts: '💬',
		skills: '🧠',
		tools: '🔧'
	};

	const onAction = () => {
		if (actionHref) {
			window.location.href = actionHref;
		} else {
			dispatch('action');
		}
	};
</script>

<div class="flex w-full flex-col items-center justify-center py-14 pb-20">
	<div class="max-w-md text-center">
		<div
			class="mx-auto mb-4 flex size-14 items-center justify-center rounded-2xl bg-gray-100 text-3xl dark:bg-gray-850"
			aria-hidden="true"
		>
			{glyphs[icon]}
		</div>

		<div class="mb-2 text-base font-medium text-gray-900 dark:text-gray-100">
			{title}
		</div>

		<div class="mb-6 text-sm leading-6 text-gray-500 dark:text-gray-400">
			{description}
		</div>

		{#if hint}
			<div
				class="mx-auto mb-6 max-w-sm rounded-xl border border-amber-200/80 bg-amber-50 px-3.5 py-3 text-xs leading-5 text-amber-800 dark:border-amber-500/25 dark:bg-amber-500/10 dark:text-amber-200"
			>
				{hint}
			</div>
		{/if}

		<div class="flex flex-wrap items-center justify-center gap-2">
			{#if actionLabel}
				<button
					class="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-gray-800 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
					type="button"
					on:click={onAction}
				>
					{actionLabel}
				</button>
			{/if}

			{#if secondaryLabel}
				<a
					class="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-850"
					href={secondaryHref || '/tutoriais'}
				>
					{secondaryLabel}
				</a>
			{/if}
		</div>
	</div>
</div>
