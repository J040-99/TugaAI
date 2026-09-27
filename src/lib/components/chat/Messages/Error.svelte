<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import Info from '$lib/components/icons/Info.svelte';
	import { getFriendlyErrorMessage } from '$lib/utils/errorMessages';

	export let content: unknown = '';
	/** Retry the message that produced this error (null hides the button). */
	export let onRetry: (() => void) | null = null;

	const i18n = getContext<Writable<i18nType>>('i18n');

	const translate = (key: string): string => {
		try {
			return $i18n?.t(key) ?? key;
		} catch {
			return key;
		}
	};

	const getErrorMessage = (value: unknown): string => {
		if (typeof value === 'string') {
			return value;
		}

		if (typeof value === 'object' && value !== null) {
			const error = 'error' in value ? (value as any).error : null;

			if (
				typeof error === 'object' &&
				error !== null &&
				'message' in error &&
				typeof error.message === 'string'
			) {
				return error.message;
			}

			if ('detail' in value && typeof (value as any).detail === 'string') {
				return (value as any).detail;
			}

			if ('message' in value && typeof (value as any).message === 'string') {
				return (value as any).message;
			}

			return JSON.stringify(value) ?? String(value);
		}

		return JSON.stringify(value) ?? String(value);
	};

	// Opens the model picker in the chat header so the user can move away from
	// a model that is refusing to answer (rate limits, outages, ...).
	const openModelSelector = () => {
		const button = document.querySelector(
			'[id^="model-selector-"][id$="-button"]'
		) as HTMLElement | null;
		button?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
		button?.click();
	};

	$: friendlyKey = getFriendlyErrorMessage(content);
	$: message = friendlyKey
		? translate(friendlyKey)
		: getErrorMessage(content) || translate('Error submitting message');
</script>

<div
	class="my-1.5 flex w-full items-start gap-2 rounded-2xl bg-black/[0.03] px-3 py-2 text-gray-500 dark:bg-white/[0.04] dark:text-gray-400"
>
	<Info className="mt-0.5 size-4 shrink-0 text-gray-400 dark:text-gray-500" strokeWidth="1.8" />

	<div class="min-w-0 flex-1 break-words text-[0.8125rem] leading-5">
		{message}

		<div class="mt-2 flex flex-wrap gap-2">
			{#if onRetry}
				<button
					type="button"
					class="rounded-lg bg-black/[0.06] px-2.5 py-1 text-xs font-medium text-gray-600 transition hover:bg-black/[0.1] dark:bg-white/[0.08] dark:text-gray-300 dark:hover:bg-white/[0.14]"
					on:click={() => onRetry?.()}
				>
					{$i18n.t('Try Again')}
				</button>
			{/if}

			<button
				type="button"
				class="rounded-lg bg-black/[0.06] px-2.5 py-1 text-xs font-medium text-gray-600 transition hover:bg-black/[0.1] dark:bg-white/[0.08] dark:text-gray-300 dark:hover:bg-white/[0.14]"
				on:click={openModelSelector}
			>
				{$i18n.t('Choose another model')}
			</button>
		</div>
	</div>
</div>
