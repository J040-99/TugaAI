<script lang="ts">
	import { marked } from 'marked';

	import { getContext, onMount, tick } from 'svelte';
	import dayjs from '$lib/dayjs';

	import { mobile, modelReliability, refreshModelReliability, settings, user } from '$lib/stores';
	import { WEBUI_API_BASE_URL, WEBUI_BASE_URL } from '$lib/constants';

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import { copyToClipboard, sanitizeResponseContent } from '$lib/utils';
	import { getModelPrice, getModelLimits, isFreeModel } from '$lib/utils/modelCategories';
	import {
		describeModelCapabilities,
		getModelCapabilityBadges,
		type ModelModalityCapability
	} from '$lib/utils/modelCapabilities';
	import { resolveLocalizedModelDescription } from '$lib/utils/localizedContent';
	import ArrowUpTray from '$lib/components/icons/ArrowUpTray.svelte';
	import Check from '$lib/components/icons/Check.svelte';
	import Photo from '$lib/components/icons/Photo.svelte';
	import Mic from '$lib/components/icons/Mic.svelte';
	import Sparkles from '$lib/components/icons/Sparkles.svelte';
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte';
	import TerminalIcon from '$lib/components/icons/Terminal.svelte';
	import ModelItemMenu from './ModelItemMenu.svelte';
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte';
	import { toast } from 'svelte-sonner';
	import Tag from '$lib/components/icons/Tag.svelte';
	import Label from '$lib/components/icons/Label.svelte';

	const i18n = getContext('i18n');

	export let selectedModelIdx: number = -1;
	export let item: any = {};
	export let index: number = -1;
	export let value: string | null = '';
	export let selectedValues: string[] = [];
	export let compareEnabled = false;

	export let unloadModelHandler: (model: any) => void = () => {};
	export let pinModelHandler: (modelId: string) => void = () => {};
	export let deleteModelHandler: (model: any) => void = () => {};
	export let selectionOnly = false;

	export let onClick: () => void = () => {};

	$: localizedDescription = resolveLocalizedModelDescription(item.model, $i18n.language);

	// Trust ranking over the last 24h — see backend utils/model_reliability.py.
	$: reliability = $modelReliability[item?.model?.id ?? item?.value ?? ''];

	onMount(() => {
		refreshModelReliability();
	});

	const copyLinkHandler = async (model) => {
		const baseUrl = window.location.origin;
		const res = await copyToClipboard(`${baseUrl}/?model=${encodeURIComponent(model.id)}`);

		if (res) {
			toast.success($i18n.t('Copied link to clipboard'));
		} else {
			toast.error($i18n.t('Failed to copy link'));
		}
	};

	const formatSize = (size?: number) => (size ? `(${(size / 1024 ** 3).toFixed(1)}GB)` : '');

	let showMenu = false;
	$: isSelected = compareEnabled ? selectedValues.includes(item.value) : value === item.value;
	$: price =
		getModelPrice(item?.model) ??
		(isFreeModel(item)
			? {
					isFree: true,
					short: 'Grátis',
					long: 'Grátis · entrada $0 · saída $0 / 1M tokens',
					inputPerM: 0,
					outputPerM: 0,
					inputLabel: '$0',
					outputLabel: '$0'
				}
			: null);
	$: priceLabel = price?.short ?? null;
	$: priceTooltip = price?.long ?? '';
	$: limits = getModelLimits(item?.model);
	$: capabilityBadges = getModelCapabilityBadges(item?.model);
	$: capabilitySummary = describeModelCapabilities(item?.model, (k) => $i18n.t(k));

	const badgeIcon = (key: ModelModalityCapability) => {
		if (key === 'vision' || key === 'image_generation') return 'image';
		if (key === 'audio_in' || key === 'audio_out') return 'audio';
		if (key === 'video_in' || key === 'video_out') return 'video';
		if (key === 'web_search') return 'web';
		if (key === 'terminal' || key === 'code_interpreter') return 'terminal';
		return 'image';
	};
</script>

<button
	role="option"
	aria-selected={isSelected}
	aria-label={[
		$i18n.t('Select {{modelName}} model', { modelName: item.label }),
		priceTooltip || priceLabel || '',
		capabilitySummary || ''
	]
		.filter(Boolean)
		.join(' — ')}
	class="focus-ring group/item flex h-8 w-full cursor-pointer select-none items-center rounded-xl px-2 text-left text-[0.8125rem] font-normal text-gray-700 outline-hidden transition-colors duration-75 dark:text-gray-100 {($settings?.highContrastMode ??
	false)
		? 'hover:bg-gray-200 dark:hover:bg-gray-800'
		: 'hover:bg-gray-50/40 dark:hover:bg-gray-800/40'} {index === selectedModelIdx &&
	!compareEnabled
		? ($settings?.highContrastMode ?? false)
			? 'bg-gray-200 dark:bg-gray-800'
			: 'bg-gray-50/70 dark:bg-gray-800/60'
		: ''} {isSelected
		? ($settings?.highContrastMode ?? false)
			? 'bg-gray-200 dark:bg-gray-800'
			: 'bg-gray-50/70 dark:bg-gray-800/60'
		: ''}"
	data-arrow-selected={index === selectedModelIdx}
	data-value={item.value}
	on:click={() => {
		onClick();
	}}
>
	<div class="flex flex-1 flex-col gap-1.5 overflow-hidden">
		<!-- {#if (item?.model?.tags ?? []).length > 0}
			<div
				class="flex gap-0.5 self-center items-start h-full w-full translate-y-[0.5px] overflow-x-auto scrollbar-none"
			>
				{#each item.model?.tags.sort((a, b) => a.name.localeCompare(b.name)) as tag}
					<Tooltip content={tag.name} className="flex-shrink-0">
						<div
							class=" text-xs font-normal px-1 rounded-sm uppercase bg-gray-500/20 text-gray-700 dark:text-gray-200"
						>
							{tag.name}
						</div>
					</Tooltip>
				{/each}
			</div>
		{/if} -->

		<div class="flex min-w-0 items-center gap-1.5 overflow-hidden">
			<div class="flex shrink-0 items-center">
				<Tooltip content={$user?.role === 'admin' ? (item?.value ?? '') : ''} placement="top-start">
					<img
						src={`${WEBUI_API_BASE_URL}/models/model/profile/image?id=${item.model.id}&lang=${$i18n.language}`}
						alt={$i18n.t('{{modelName}} profile image', { modelName: item.label })}
						class="flex size-4 items-center rounded-full"
						loading="lazy"
						on:error={(e) => {
							// LICENSE covers this Open WebUI fallback logo.
							// Do not alter, remove, obscure, or replace it except as LICENSE permits:
							// https://docs.openwebui.com/license.
							e.currentTarget.src = '/favicon.png';
						}}
					/>
				</Tooltip>
			</div>

			<!-- Name: plain truncate (no Tooltip wrapper — tippy div breaks min-w-0 chain) -->
			<div class="flex min-w-0 flex-1 items-center overflow-hidden">
				<div
					class="w-full truncate leading-tight"
					title={`${item.label} (${item.value})${limits ? ` · ${limits.long}` : ''}${capabilitySummary ? ` · ${capabilitySummary}` : ''}${priceTooltip ? ` · ${priceTooltip}` : ''}`}
				>
					{item.label}
				</div>
			</div>

			<!-- Reliability: trust ranking over the last 24h (dot + score) -->
			{#if reliability}
				<div class="flex shrink-0 items-center">
					<Tooltip
						content={`${$i18n.t('Reliability')}: ${Math.round(reliability.score * 100)}% · ${reliability.successes}/${reliability.observations} · ${$i18n.t('Last 24 hours')}`}
						placement="top"
						className="flex shrink-0"
					>
						<span
							class="flex items-center gap-1 whitespace-nowrap text-[0.6875rem] font-medium tabular-nums {reliability.status ===
							'available'
								? 'text-emerald-600 dark:text-emerald-400'
								: reliability.status === 'busy'
									? 'text-amber-600 dark:text-amber-400'
									: 'text-red-500 dark:text-red-400'}"
							aria-label={`${$i18n.t('Reliability')} ${Math.round(reliability.score * 100)}%`}
						>
							<span
								class="size-1.5 rounded-full {reliability.status === 'available'
									? 'bg-emerald-500'
									: reliability.status === 'busy'
										? 'bg-amber-500'
										: 'bg-red-500'}"
							/>
							{Math.round(reliability.score * 100)}%
						</span>
					</Tooltip>
				</div>
			{/if}

			<!-- Price: compact, always right of name, never wraps -->
			{#if priceLabel}
				<div class="flex shrink-0 items-center">
					<Tooltip
						content={priceTooltip || priceLabel}
						placement="top-end"
						className="flex shrink-0"
					>
						<span
							class="whitespace-nowrap text-[0.6875rem] font-medium tabular-nums {price?.isFree
								? 'text-emerald-600 dark:text-emerald-400'
								: 'text-gray-500 dark:text-gray-400'}"
						>
							{#if price?.isFree}
								{priceLabel}
							{:else if price && (price.inputLabel || price.outputLabel)}
								{#if price.inputLabel && price.outputLabel && price.inputLabel !== price.outputLabel}
									{price.inputLabel}/{price.outputLabel}
								{:else}
									{price.inputLabel ?? price.outputLabel}
								{/if}
							{:else}
								{priceLabel}
							{/if}
						</span>
					</Tooltip>
				</div>
			{/if}

			<!-- Capabilities: max 2 icons -->
			{#if capabilityBadges.length > 0}
				<div class="flex shrink-0 items-center">
					<Tooltip content={capabilitySummary} placement="top" className="flex shrink-0">
						<span class="flex items-center gap-0.5" aria-label={capabilitySummary}>
							{#each capabilityBadges.slice(0, 2) as badge (badge.key)}
								<span
									class="flex size-[0.9375rem] items-center justify-center text-gray-400 dark:text-gray-500"
									title={$i18n.t(badge.labelKey)}
									aria-label={$i18n.t(badge.labelKey)}
								>
									{#if badge.key === 'vision'}
										<Photo className="size-3" strokeWidth="1.5" />
									{:else if badge.key === 'audio_in' || badge.key === 'audio_out'}
										<Mic className="size-3" strokeWidth="1.5" />
									{:else if badge.key === 'video_in' || badge.key === 'video_out'}
										<svg
											xmlns="http://www.w3.org/2000/svg"
											viewBox="0 0 16 16"
											fill="currentColor"
											class="size-3"
											aria-hidden="true"
										>
											<path
												d="M2 4.75A.75.75 0 0 1 2.75 4h7.5a.75.75 0 0 1 .75.75v6.5a.75.75 0 0 1-.75.75h-7.5a.75.75 0 0 1-.75-.75v-6.5Zm9.22 1.22a.75.75 0 0 1 1.06 0l1.25 1.25a.75.75 0 0 1 0 1.06l-1.25 1.25a.75.75 0 1 1-1.06-1.06l.72-.72.72.72a.75.75 0 1 1-1.06 1.06L11.56 8.72l-.72.72a.75.75 0 1 1-1.06-1.06l.72-.72-.72-.72a.75.75 0 0 1 0-1.06l1.25-1.25Z"
											/>
										</svg>
									{:else if badge.key === 'image_generation'}
										<Sparkles className="size-3" strokeWidth="1.5" />
									{:else if badge.key === 'web_search'}
										<GlobeAlt className="size-3" strokeWidth="1.5" />
									{:else if badge.key === 'terminal' || badge.key === 'code_interpreter'}
										<TerminalIcon className="size-3" strokeWidth="1.5" />
									{/if}
								</span>
							{/each}
							{#if capabilityBadges.length > 2}
								<span class="text-[0.625rem] text-gray-400 dark:text-gray-500"
									>+{capabilityBadges.length - 2}</span
								>
							{/if}
						</span>
					</Tooltip>
				</div>
			{/if}

			<!-- Secondary meta: only on hover so the name stays readable (display:none frees space) -->
			<div class="hidden shrink-0 items-center gap-1.5 group-hover/item:flex">
				{#if limits}
					<div class="flex items-center">
						<Tooltip content={limits.long} placement="top">
							<span
								class="whitespace-nowrap text-[0.6875rem] font-normal tabular-nums text-gray-400 dark:text-gray-500"
							>
								{limits.short}
							</span>
						</Tooltip>
					</div>
				{/if}

				{#if item.model.owned_by === 'ollama'}
					{#if (item.model.ollama?.details?.parameter_size ?? '') !== ''}
						<div class="flex items-center translate-y-[0.5px]">
							<Tooltip
								content={`${
									item.model.ollama?.details?.quantization_level
										? item.model.ollama?.details?.quantization_level + ' '
										: ''
								}${
									item.model.ollama?.size
										? `(${(item.model.ollama?.size / 1024 ** 3).toFixed(1)}GB)`
										: ''
								}`}
								className="self-end"
							>
								<span
									class="line-clamp-1 text-[0.6875rem] font-normal text-gray-500 dark:text-gray-400"
									>{item.model.ollama?.details?.parameter_size ?? ''}</span
								>
							</Tooltip>
						</div>
					{/if}
				{:else if item.model.provider === 'lmstudio' || item.model.provider === 'llama.cpp'}
					{@const parameterSize =
						item.model.params_string ?? item.model.details?.parameter_size ?? ''}
					{@const quantization =
						item.model.quantization?.name ?? item.model.details?.quantization_level ?? ''}
					{@const size = item.model.size_bytes ?? item.model.size}
					{#if parameterSize || quantization || size}
						<div class="flex items-center translate-y-[0.5px]">
							<Tooltip
								content={`${quantization ? `${quantization} ` : ''}${formatSize(size)}`}
								className="self-end"
							>
								<span
									class="line-clamp-1 text-[0.6875rem] font-normal text-gray-500 dark:text-gray-400"
								>
									{parameterSize || quantization || formatSize(size)}
								</span>
							</Tooltip>
						</div>
					{/if}
				{/if}

				{#if item.model.loaded}
					<div class="flex items-center px-0.5">
						<Tooltip
							content={item.model.ollama?.expires_at &&
							new Date(item.model.ollama?.expires_at * 1000) > new Date()
								? `${$i18n.t('Unloads {{FROM_NOW}}', {
										FROM_NOW: dayjs(item.model.ollama?.expires_at * 1000).fromNow()
									})}`
								: `${$i18n.t('Loaded')}`}
							className="self-end"
						>
							<div class=" flex items-center">
								<span class="relative flex size-1.5">
									<span
										class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"
									/>
									<span class="relative inline-flex size-1.5 rounded-full bg-green-500" />
								</span>
							</div>
						</Tooltip>
					</div>
				{/if}

				<!-- {JSON.stringify(item.info)} -->

				{#if (item?.model?.tags ?? []).length > 0}
					{#key item.model.id}
						<Tooltip elementId="tags-{item.model.id}">
							<div slot="tooltip" id="tags-{item.model.id}">
								{#each item.model?.tags.sort((a, b) => a.name.localeCompare(b.name)) as tag}
									<Tooltip content={tag.name} className="flex-shrink-0">
										<div class=" text-xs font-normal rounded-sm uppercase text-white">
											{tag.name}
										</div>
									</Tooltip>
								{/each}
							</div>

							<div class="translate-y-[1px]">
								<Tag />
							</div>
						</Tooltip>
					{/key}
				{/if}

				{#if item.model?.direct}
					<Tooltip content={`${$i18n.t('Direct')}`}>
						<div class="translate-y-[1px]">
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 16 16"
								fill="currentColor"
								class="size-3"
							>
								<path
									fill-rule="evenodd"
									d="M2 2.75A.75.75 0 0 1 2.75 2C8.963 2 14 7.037 14 13.25a.75.75 0 0 1-1.5 0c0-5.385-4.365-9.75-9.75-9.75A.75.75 0 0 1 2 2.75Zm0 4.5a.75.75 0 0 1 .75-.75 6.75 6.75 0 0 1 6.75 6.75.75.75 0 0 1-1.5 0C8 10.35 5.65 8 2.75 8A.75.75 0 0 1 2 7.25ZM3.5 11a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3Z"
									clip-rule="evenodd"
								/>
							</svg>
						</div>
					</Tooltip>
				{:else if item.model.connection_type === 'external'}
					<Tooltip content={`${$i18n.t('External')}`}>
						<div class="translate-y-[1px]">
							<svg
								xmlns="http://www.w3.org/2000/svg"
								viewBox="0 0 16 16"
								fill="currentColor"
								class="size-3"
							>
								<path
									fill-rule="evenodd"
									d="M8.914 6.025a.75.75 0 0 1 1.06 0 3.5 3.5 0 0 1 0 4.95l-2 2a3.5 3.5 0 0 1-5.396-4.402.75.75 0 0 1 1.251.827 2 2 0 0 0 3.085 2.514l2-2a2 2 0 0 0 0-2.828.75.75 0 0 1 0-1.06Z"
									clip-rule="evenodd"
								/>
								<path
									fill-rule="evenodd"
									d="M7.086 9.975a.75.75 0 0 1-1.06 0 3.5 3.5 0 0 1 0-4.95l2-2a3.5 3.5 0 0 1 5.396 4.402.75.75 0 0 1-1.251-.827 2 2 0 0 0-3.085-2.514l-2 2a2 2 0 0 0 0 2.828.75.75 0 0 1 0 1.06Z"
									clip-rule="evenodd"
								/>
							</svg>
						</div>
					</Tooltip>
				{/if}

				{#if localizedDescription}
					<Tooltip
						content={`${marked.parse(
							sanitizeResponseContent(localizedDescription).replaceAll('\n', '<br>')
						)}`}
					>
						<div class=" translate-y-[1px]">
							<svg
								xmlns="http://www.w3.org/2000/svg"
								fill="none"
								viewBox="0 0 24 24"
								stroke-width="1.5"
								stroke="currentColor"
								class="w-4 h-4"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z"
								/>
							</svg>
						</div>
					</Tooltip>
				{/if}
			</div>
		</div>
	</div>

	<div class="ml-auto flex shrink-0 items-center gap-1.5 pl-2">
		{#if !selectionOnly && $user?.role === 'admin' && item.model.loaded}
			<Tooltip
				content={`${$i18n.t('Eject')}`}
				className="flex-shrink-0 group-hover/item:opacity-100 opacity-0 "
			>
				<button
					class="focus-ring flex"
					aria-label={$i18n.t('Eject model')}
					on:click={(e) => {
						e.preventDefault();
						e.stopPropagation();
						unloadModelHandler(item.value);
					}}
				>
					<ArrowUpTray className="size-3" />
				</button>
			</Tooltip>
		{/if}

		{#if !selectionOnly}
			<ModelItemMenu
				bind:show={showMenu}
				model={item.model}
				{pinModelHandler}
				{deleteModelHandler}
				copyLinkHandler={() => {
					copyLinkHandler(item.model);
				}}
			>
				<button
					aria-label={`${$i18n.t('More Options')}`}
					class="focus-ring flex"
					on:click={(e) => {
						e.preventDefault();
						e.stopPropagation();
						showMenu = !showMenu;
					}}
				>
					<EllipsisHorizontal />
				</button>
			</ModelItemMenu>
		{/if}

		{#if isSelected}
			<div>
				<Check className="size-3" />
			</div>
		{/if}
	</div>
</button>
