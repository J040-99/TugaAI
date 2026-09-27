<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import dayjs from 'dayjs';

	import { getUserUsage, updateUserSettings, getUserSettings } from '$lib/apis/users';
	import { models, showSidebar, mobile } from '$lib/stores';
	import { getModelPrice } from '$lib/utils/modelCategories';
	import { formatNumber } from '$lib/utils';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import ChartBar from '$lib/components/icons/ChartBar.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
	import Trash from '$lib/components/icons/Trash.svelte';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';

	const i18n = getContext('i18n');

	type SpendLimit = {
		id: string;
		period: 'monthly' | 'daily';
		amount: number;
		currency: 'USD' | 'EUR';
		enabled: boolean;
	};

	type SpendingSettings = {
		limits: SpendLimit[];
		alertThreshold: number;
	};

	const DEFAULT_SETTINGS: SpendingSettings = {
		limits: [],
		alertThreshold: 80
	};

	let loading = true;
	let saving = false;
	let usage: any = null;
	let spending: SpendingSettings = { ...DEFAULT_SETTINGS };

	let showAddForm = false;
	let newLimit: Omit<SpendLimit, 'id'> = {
		period: 'monthly',
		amount: 20,
		currency: 'USD',
		enabled: true
	};

	const money = (value: number, currency: 'USD' | 'EUR' = 'USD') => {
		const symbol = currency === 'EUR' ? '€' : '$';
		const n = Number(value) || 0;
		if (n === 0) return `${symbol}0`;
		if (n < 0.01) return `${symbol}${n.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')}`;
		return `${symbol}${n.toFixed(2)}`;
	};

	const periodStart = (period: 'month' | 'day') => {
		const d = period === 'month' ? dayjs().startOf('month') : dayjs().startOf('day');
		return d.unix();
	};

	const modelPricingById = () => {
		const map = new Map<string, ReturnType<typeof getModelPrice>>();
		for (const m of $models ?? []) {
			const price = getModelPrice(m);
			if (price) map.set(m.id, price);
		}
		return map;
	};

	const estimateModelCost = (
		entry: { model_id: string; input_tokens?: number; output_tokens?: number },
		pricing: Map<string, ReturnType<typeof getModelPrice>>
	) => {
		const p = pricing.get(entry.model_id);
		if (!p) return null;
		const input = entry.input_tokens ?? 0;
		const output = entry.output_tokens ?? 0;
		if (p.isFree) return 0;
		const inCost = ((p.inputPerM ?? 0) * input) / 1_000_000;
		const outCost = ((p.outputPerM ?? 0) * output) / 1_000_000;
		return inCost + outCost;
	};

	const loadUsage = async () => {
		loading = true;
		try {
			const start = periodStart('month');
			const end = dayjs().endOf('day').unix();
			usage = await getUserUsage(localStorage.token, { startDate: start, endDate: end });
		} catch (e) {
			console.error(e);
			usage = null;
		} finally {
			loading = false;
		}
	};

	const loadSettings = async () => {
		try {
			const settings = await getUserSettings(localStorage.token);
			const raw = settings?.spending;
			if (raw && typeof raw === 'object') {
				spending = {
					limits: Array.isArray(raw.limits) ? raw.limits : [],
					alertThreshold:
						typeof raw.alertThreshold === 'number' ? raw.alertThreshold : DEFAULT_SETTINGS.alertThreshold
				};
			}
		} catch (e) {
			console.error(e);
		}
	};

	const persist = async () => {
		if (!localStorage.token) return;
		saving = true;
		try {
			await updateUserSettings(localStorage.token, { spending: spending });
		} catch (e) {
			console.error(e);
		} finally {
			saving = false;
		}
	};

	const addLimit = async () => {
		const amount = Number(newLimit.amount);
		if (!Number.isFinite(amount) || amount <= 0) return;
		spending.limits = [
			...spending.limits,
			{
				...newLimit,
				id: `limit_${Date.now().toString(36)}`,
				amount
			}
		];
		showAddForm = false;
		newLimit = { period: 'monthly', amount: 20, currency: 'USD', enabled: true };
		await persist();
	};

	const removeLimit = async (id: string) => {
		spending.limits = spending.limits.filter((l) => l.id !== id);
		await persist();
	};

	const toggleLimit = async (limit: SpendLimit) => {
		spending.limits = spending.limits.map((l) =>
			l.id === limit.id ? { ...l, enabled: !l.enabled } : l
		);
		await persist();
	};

	const updateLimitAmount = async (limit: SpendLimit, amount: number) => {
		if (!Number.isFinite(amount) || amount <= 0) return;
		spending.limits = spending.limits.map((l) => (l.id === limit.id ? { ...l, amount } : l));
		await persist();
	};

	$: pricingMap = modelPricingById();

	$: monthUsage = usage;
	$: topModels = (monthUsage?.top_models ?? []) as {
		model_id: string;
		messages: number;
		input_tokens: number;
		output_tokens: number;
		total_tokens: number;
	}[];

	$: modelCosts = topModels.map((entry) => {
		const cost = estimateModelCost(entry, pricingMap);
		return {
			...entry,
			cost,
			name: $models?.find((m) => m.id === entry.model_id)?.name ?? entry.model_id
		};
	});

	$: knownCost = modelCosts.reduce((sum, m) => sum + (m.cost ?? 0), 0);
	$: hasPricing = modelCosts.some((m) => m.cost !== null);
	$: periodCost = knownCost;

	$: totalTokens = monthUsage?.totals?.input_tokens + monthUsage?.totals?.output_tokens || 0;
	$: totalMessages = monthUsage?.totals?.messages ?? 0;
	$: modelsUsed = monthUsage?.totals?.models_used ?? 0;
	$: activeDays = monthUsage?.totals?.active_days ?? 0;

	$: dailySeries = (monthUsage?.heatmap ?? []).map((day: any) => ({
		date: day.date,
		tokens: day.tokens ?? 0,
		messages: day.messages ?? 0
	}));

	$: maxDailyTokens = Math.max(1, ...dailySeries.map((d: any) => d.tokens));

	$: monthLimit = spending.limits.find((l) => l.period === 'monthly' && l.enabled);
	$: dayLimit = spending.limits.find((l) => l.period === 'daily' && l.enabled);

	$: todayTokens =
		dailySeries.find((d: any) => d.date === dayjs().format('YYYY-MM-DD'))?.tokens ?? 0;

	$: monthPct = monthLimit && monthLimit.amount > 0 ? (periodCost / monthLimit.amount) * 100 : 0;
	$: dayPctEstimate = (() => {
		if (!dayLimit || dayLimit.amount <= 0 || totalTokens <= 0) return 0;
		const costPerToken = periodCost / totalTokens;
		return ((todayTokens * costPerToken) / dayLimit.amount) * 100;
	})();

	$: overMonth = monthLimit ? periodCost >= monthLimit.amount : false;
	$: overDay = dayLimit && totalTokens > 0 ? dayPctEstimate >= 100 : false;
	$: alertMonth =
		monthLimit && spending.alertThreshold > 0
			? monthPct >= spending.alertThreshold
			: false;

	onMount(async () => {
		await Promise.all([loadSettings(), loadUsage()]);
	});
</script>

<svelte:head>
	<title>{$i18n.t('Spending')} · TugaAI</title>
</svelte:head>

<div class="flex h-full w-full flex-col overflow-x-hidden">
	<div
		class="flex flex-1 flex-col overflow-y-auto overflow-x-hidden px-4 pt-4 pb-10 md:px-6 md:pt-6"
	>
		<div class="mx-auto w-full max-w-4xl">
			<div class="mb-6 flex items-start justify-between gap-3">
				<div class="min-w-0">
					<div class="mb-1 flex items-center gap-2">
						<ChartBar className="size-5 text-gray-500 dark:text-gray-400" strokeWidth="1.5" />
						<h1 class="text-xl font-semibold text-gray-900 dark:text-white">
							{$i18n.t('Spending')}
						</h1>
					</div>
					<p class="text-sm text-gray-500 dark:text-gray-400">
						{$i18n.t(
							'Estimated spend from your token usage and current model prices. You pay OpenRouter directly.'
						)}
					</p>
				</div>
				<button
					type="button"
					class="focus-ring shrink-0 rounded-xl border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 transition hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
					on:click={loadUsage}
					disabled={loading}
				>
					{$i18n.t('Refresh')}
				</button>
			</div>

			{#if overMonth || overDay || alertMonth}
				<div
					class="mb-5 rounded-xl border px-4 py-3 text-sm {overMonth || overDay
						? 'border-red-200 bg-red-50 text-red-800 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300'
						: 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300'}"
					role="status"
				>
					{#if overMonth}
						{$i18n.t('Monthly spending limit reached.')}
					{:else if overDay}
						{$i18n.t('Daily spending limit reached.')}
					{:else}
						{$i18n.t('You are approaching your monthly spending limit ({{percent}}%).', {
							percent: Math.round(monthPct)
						})}
					{/if}
				</div>
			{/if}

			{#if loading}
				<div class="flex items-center justify-center py-16">
					<Spinner />
				</div>
			{:else}
				<!-- Summary cards -->
				<div class="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
					<div
						class="rounded-2xl border border-gray-100 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900"
					>
						<div class="text-[0.6875rem] uppercase tracking-wide text-gray-400">
							{$i18n.t('This month')}
						</div>
						<div class="mt-1 text-lg font-semibold tabular-nums text-gray-900 dark:text-white">
							{#if hasPricing}
								{money(periodCost, monthLimit?.currency ?? 'USD')}
							{:else}
								—
							{/if}
						</div>
						<div class="text-[0.6875rem] text-gray-400">
							{#if hasPricing}
								{$i18n.t('estimated')}
							{:else}
								{$i18n.t('No pricing data')}
							{/if}
						</div>
					</div>

					<div
						class="rounded-2xl border border-gray-100 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900"
					>
						<div class="text-[0.6875rem] uppercase tracking-wide text-gray-400">
							{$i18n.t('Tokens')}
						</div>
						<div class="mt-1 text-lg font-semibold tabular-nums text-gray-900 dark:text-white">
							{formatNumber(totalTokens)}
						</div>
						<div class="text-[0.6875rem] text-gray-400">
							{formatNumber(monthUsage?.totals?.input_tokens ?? 0)} in · {formatNumber(
								monthUsage?.totals?.output_tokens ?? 0
							)} out
						</div>
					</div>

					<div
						class="rounded-2xl border border-gray-100 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900"
					>
						<div class="text-[0.6875rem] uppercase tracking-wide text-gray-400">
							{$i18n.t('Messages')}
						</div>
						<div class="mt-1 text-lg font-semibold tabular-nums text-gray-900 dark:text-white">
							{formatNumber(totalMessages)}
						</div>
						<div class="text-[0.6875rem] text-gray-400">
							{formatNumber(activeDays)} {$i18n.t('active days')}
						</div>
					</div>

					<div
						class="rounded-2xl border border-gray-100 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900"
					>
						<div class="text-[0.6875rem] uppercase tracking-wide text-gray-400">
							{$i18n.t('Models')}
						</div>
						<div class="mt-1 text-lg font-semibold tabular-nums text-gray-900 dark:text-white">
							{formatNumber(modelsUsed)}
						</div>
						<div class="text-[0.6875rem] text-gray-400">{$i18n.t('used this period')}</div>
					</div>
				</div>

				<!-- Daily activity -->
				<section
					class="mb-6 rounded-2xl border border-gray-100 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900"
				>
					<div class="mb-3 flex items-center justify-between">
						<h2 class="text-sm font-medium text-gray-900 dark:text-white">
							{$i18n.t('Daily token usage')}
						</h2>
						<span class="text-[0.6875rem] text-gray-400">
							{$i18n.t('Current month')}
						</span>
					</div>

					{#if dailySeries.length === 0}
						<p class="py-6 text-center text-sm text-gray-400">
							{$i18n.t('No usage yet this month.')}
						</p>
					{:else}
						<div class="flex h-28 items-end gap-[3px]" role="img" aria-label={$i18n.t('Daily token usage')}>
							{#each dailySeries as day (day.date)}
								{@const h = Math.max(4, Math.round((day.tokens / maxDailyTokens) * 100))}
								<Tooltip
									content="{day.date}: {formatNumber(day.tokens)} {$i18n.t('tokens')} · {formatNumber(
										day.messages
									)} {$i18n.t('messages')}"
									placement="top"
								>
									<div class="flex h-full flex-1 items-end">
										<div
											class="w-full rounded-t {day.date === dayjs().format('YYYY-MM-DD')
												? 'bg-blue-500'
												: 'bg-blue-300 dark:bg-blue-700/70'}"
											style="height: {h}%"
										/>
									</div>
								</Tooltip>
							{/each}
						</div>
					{/if}
				</section>

				<!-- Limits -->
				<section
					class="mb-6 rounded-2xl border border-gray-100 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900"
				>
					<div class="mb-4 flex flex-wrap items-center justify-between gap-2">
						<div>
							<h2 class="text-sm font-medium text-gray-900 dark:text-white">
								{$i18n.t('Spending limits')}
							</h2>
							<p class="text-xs text-gray-400">
								{$i18n.t('Warn when estimated spend crosses these thresholds. Stored on your account.')}
							</p>
						</div>
						<button
							type="button"
							class="focus-ring flex items-center gap-1 rounded-xl border border-gray-200 px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
							on:click={() => (showAddForm = !showAddForm)}
						>
							<Plus className="size-3.5" />
							{$i18n.t('New limit')}
						</button>
					</div>

					<div class="mb-4 flex flex-wrap items-center gap-3">
						<label class="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300">
							{$i18n.t('Alert at')}
							<input
								type="number"
								min="10"
								max="100"
								step="5"
								class="focus-ring w-16 rounded-lg border border-gray-200 bg-transparent px-2 py-1 text-right text-xs tabular-nums dark:border-gray-700"
								value={spending.alertThreshold}
								on:change={async (e) => {
									const v = Number(e.currentTarget.value);
									spending.alertThreshold = Math.min(100, Math.max(10, v || 80));
									await persist();
								}}
							/>
							%
						</label>
						{#if saving}
							<span class="text-[0.6875rem] text-gray-400">{$i18n.t('Saving…')}</span>
						{/if}
					</div>

					{#if showAddForm}
						<div
							class="mb-4 flex flex-wrap items-end gap-3 rounded-xl border border-dashed border-gray-200 p-3 dark:border-gray-700"
						>
							<label class="flex flex-col gap-1 text-[0.6875rem] text-gray-500">
								{$i18n.t('Period')}
								<select
									class="focus-ring rounded-lg border border-gray-200 bg-transparent px-2 py-1.5 text-xs text-gray-800 dark:border-gray-700 dark:text-gray-200"
									bind:value={newLimit.period}
								>
									<option value="monthly">{$i18n.t('Monthly')}</option>
									<option value="daily">{$i18n.t('Daily')}</option>
								</select>
							</label>
							<label class="flex flex-col gap-1 text-[0.6875rem] text-gray-500">
								{$i18n.t('Amount')}
								<input
									type="number"
									min="0.01"
									step="0.01"
									class="focus-ring w-28 rounded-lg border border-gray-200 bg-transparent px-2 py-1.5 text-xs tabular-nums dark:border-gray-700"
									bind:value={newLimit.amount}
								/>
							</label>
							<label class="flex flex-col gap-1 text-[0.6875rem] text-gray-500">
								{$i18n.t('Currency')}
								<select
									class="focus-ring rounded-lg border border-gray-200 bg-transparent px-2 py-1.5 text-xs text-gray-800 dark:border-gray-700 dark:text-gray-200"
									bind:value={newLimit.currency}
								>
									<option value="USD">USD ($)</option>
									<option value="EUR">EUR (€)</option>
								</select>
							</label>
							<button
								type="button"
								class="focus-ring rounded-xl bg-gray-900 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-gray-800 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
								on:click={addLimit}
							>
								{$i18n.t('Add')}
							</button>
							<button
								type="button"
								class="focus-ring rounded-xl px-2 py-1.5 text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
								on:click={() => (showAddForm = false)}
							>
								{$i18n.t('Cancel')}
							</button>
						</div>
					{/if}

					{#if spending.limits.length === 0}
						<p class="py-4 text-center text-sm text-gray-400">
							{$i18n.t('No spending limits yet. Create one to track your budget.')}
						</p>
					{:else}
						<ul class="space-y-3">
							{#each spending.limits as limit (limit.id)}
								{@const pct =
									limit.period === 'monthly'
										? monthPct
										: dayPctEstimate}
								{@const used = limit.period === 'monthly' ? periodCost : dayPctEstimate * (limit.amount / 100)}
								<li class="rounded-xl border border-gray-100 p-3 dark:border-gray-800">
									<div class="mb-2 flex items-center justify-between gap-3">
										<div class="flex min-w-0 items-center gap-2">
											<span class="text-sm font-medium text-gray-800 dark:text-gray-100">
												{limit.period === 'monthly' ? $i18n.t('Monthly') : $i18n.t('Daily')}
											</span>
											<span class="text-xs text-gray-400">·</span>
											<input
												type="number"
												min="0.01"
												step="0.01"
												class="focus-ring w-20 rounded-lg border border-transparent bg-transparent px-1 py-0.5 text-sm font-semibold tabular-nums text-gray-900 transition hover:border-gray-200 focus:border-gray-300 dark:text-white dark:hover:border-gray-700"
												value={limit.amount}
												on:change={(e) =>
													updateLimitAmount(limit, Number(e.currentTarget.value))}
											/>
											<span class="text-xs text-gray-400">{limit.currency}</span>
										</div>
										<div class="flex shrink-0 items-center gap-2">
											<Switch state={limit.enabled} on:change={() => toggleLimit(limit)} />
											<button
												type="button"
												class="focus-ring rounded-lg p-1 text-gray-400 transition hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
												aria-label={$i18n.t('Delete')}
												on:click={() => removeLimit(limit.id)}
											>
												<Trash className="size-3.5" />
											</button>
										</div>
									</div>

									{#if limit.enabled}
										<div class="mb-1.5 flex items-center justify-between text-[0.6875rem]">
											<span class="text-gray-500 dark:text-gray-400">
												{limit.period === 'monthly'
													? money(periodCost, limit.currency)
													: money(used, limit.currency)}
												/ {money(limit.amount, limit.currency)}
											</span>
											<span
												class="tabular-nums {pct >= 100
													? 'text-red-500'
													: pct >= spending.alertThreshold
														? 'text-amber-500'
														: 'text-gray-400'}"
											>
												{Math.round(pct)}%
											</span>
										</div>
										<div class="h-1.5 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
											<div
												class="h-full rounded-full transition-all {pct >= 100
													? 'bg-red-500'
													: pct >= spending.alertThreshold
														? 'bg-amber-400'
														: 'bg-emerald-500'}"
												style="width: {Math.min(100, Math.max(0, pct))}%"
											/>
										</div>
									{/if}
								</li>
							{/each}
						</ul>
					{/if}
				</section>

				<!-- Top models by cost -->
				<section
					class="rounded-2xl border border-gray-100 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900"
				>
					<h2 class="mb-3 text-sm font-medium text-gray-900 dark:text-white">
						{$i18n.t('Top models by estimated cost')}
					</h2>

					{#if modelCosts.length === 0}
						<p class="py-6 text-center text-sm text-gray-400">
							{$i18n.t('No model usage this month.')}
						</p>
					{:else}
						<div class="overflow-x-auto">
							<table class="w-full text-left text-sm">
								<thead>
									<tr class="border-b border-gray-100 text-[0.6875rem] uppercase tracking-wide text-gray-400 dark:border-gray-800">
										<th class="pb-2 pr-3 font-medium">{$i18n.t('Model')}</th>
										<th class="pb-2 pr-3 text-right font-medium">{$i18n.t('Msgs')}</th>
										<th class="pb-2 pr-3 text-right font-medium">{$i18n.t('Tokens')}</th>
										<th class="pb-2 text-right font-medium">{$i18n.t('Cost')}</th>
									</tr>
								</thead>
								<tbody>
									{#each modelCosts as row (row.model_id)}
										<tr class="border-b border-gray-50 last:border-0 dark:border-gray-800/50">
											<td class="max-w-[12rem] truncate py-2 pr-3 text-gray-800 dark:text-gray-100">
												{row.name}
											</td>
											<td class="py-2 pr-3 text-right tabular-nums text-gray-500">
												{formatNumber(row.messages)}
											</td>
											<td class="py-2 pr-3 text-right tabular-nums text-gray-500">
												{formatNumber(row.total_tokens)}
											</td>
											<td class="py-2 text-right tabular-nums font-medium text-gray-800 dark:text-gray-100">
												{#if row.cost === null}
													<span class="text-gray-400">—</span>
												{:else}
													{money(row.cost)}
												{/if}
											</td>
										</tr>
									{/each}
								</tbody>
								<tfoot>
									<tr class="border-t border-gray-100 dark:border-gray-800">
										<td colspan="3" class="pt-2 text-xs text-gray-400">
											{$i18n.t('Total (known pricing)')}
										</td>
										<td class="pt-2 text-right text-sm font-semibold tabular-nums text-gray-900 dark:text-white">
											{money(knownCost)}
										</td>
									</tr>
								</tfoot>
							</table>
						</div>
						{#if !hasPricing}
							<p class="mt-3 text-xs text-gray-400">
								{$i18n.t('Some models have no pricing metadata; their cost is not included.')}
							</p>
						{/if}
					{/if}
				</section>

				<p class="mt-6 text-center text-[0.6875rem] text-gray-400">
					{$i18n.t(
						'Costs are estimates based on token counts and provider list prices. Final charges are on your OpenRouter invoice.'
					)}
				</p>
			{/if}
		</div>
	</div>
</div>
