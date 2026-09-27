export type ModelCategoryKey = 'used' | 'popular' | 'free' | 'other';

export const MODEL_CATEGORY_ORDER: ModelCategoryKey[] = [
	'used',
	'popular',
	'free',
	'other'
];

/** OpenRouter prices are USD per token (string). Convert to $/1M tokens. */
const perMillion = (value: unknown): number | null => {
	if (value === null || value === undefined || value === '') return null;
	const n = Number(value);
	if (!Number.isFinite(n) || n < 0) return null;
	return n * 1_000_000;
};

const formatUsd = (n: number): string => {
	if (n === 0) return '$0';
	if (n < 0.01) return `$${n.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')}`;
	if (n < 1) return `$${n.toFixed(2).replace(/0+$/, '').replace(/\.$/, '')}`;
	return `$${n.toFixed(n < 100 ? 2 : 0)}`;
};

export type ModelPriceInfo = {
	isFree: boolean;
	inputPerM: number | null;
	outputPerM: number | null;
	/** Compact label e.g. "in $0.15 · out $0.60" or "Grátis" */
	short: string;
	/** Longer tooltip with explicit input/output */
	long: string;
	/** Short "in" badge text e.g. "$0.15" */
	inputLabel: string | null;
	/** Short "out" badge text e.g. "$0.60" */
	outputLabel: string | null;
};

export const getModelPrice = (model: any): ModelPriceInfo | null => {
	const pricing = model?.pricing ?? model?.info?.pricing ?? null;
	const inputPerM =
		perMillion(pricing?.prompt ?? pricing?.input) ??
		perMillion(pricing?.prompt_per_token) ??
		null;
	const outputPerM =
		perMillion(pricing?.completion ?? pricing?.output) ??
		perMillion(pricing?.completion_per_token) ??
		null;

	const id = String(model?.id ?? '').toLowerCase();
	const freeByTag =
		id.endsWith(':free') ||
		id.includes(':free:') ||
		(model?.tags ?? []).some((t: any) =>
			String(typeof t === 'string' ? t : (t?.name ?? '')).toLowerCase().includes('free')
		);

	if (
		freeByTag ||
		((inputPerM === null || inputPerM === 0) && (outputPerM === null || outputPerM === 0) &&
			(inputPerM !== null || outputPerM !== null))
	) {
		return {
			isFree: true,
			inputPerM: 0,
			outputPerM: 0,
			short: 'Grátis',
			long: 'Grátis · entrada $0 · saída $0 / 1M tokens',
			inputLabel: '$0',
			outputLabel: '$0'
		};
	}

	if (inputPerM === null && outputPerM === null) {
		return null;
	}

	const inputLabel = inputPerM !== null ? formatUsd(inputPerM) : null;
	const outputLabel = outputPerM !== null ? formatUsd(outputPerM) : null;

	const parts: string[] = [];
	if (inputLabel !== null) parts.push(`in ${inputLabel}`);
	if (outputLabel !== null) parts.push(`out ${outputLabel}`);

	const short = parts.join(' · ');
	const longParts: string[] = [];
	if (inputPerM !== null) {
		longParts.push(`Entrada (input): ${formatUsd(inputPerM)} / 1M tokens`);
	}
	if (outputPerM !== null) {
		longParts.push(`Saída (output): ${formatUsd(outputPerM)} / 1M tokens`);
	}

	return {
		isFree: false,
		inputPerM,
		outputPerM,
		short,
		long: longParts.join(' · '),
		inputLabel,
		outputLabel
	};
};

/** Back-compat helper used by ModelItem / tooltips. */
export const formatModelPrice = (model: any): string | null => getModelPrice(model)?.short ?? null;

export type ModelLimitsInfo = {
	/** Context window in tokens (prompt + completion), if known */
	contextTokens: number | null;
	/** Max output/completion tokens, if known */
	maxOutputTokens: number | null;
	/** Compact e.g. "128K ctx · 4K out" */
	short: string;
	/** Longer tooltip */
	long: string;
};

const formatTokens = (n: number): string => {
	if (n >= 1_000_000) {
		const m = n / 1_000_000;
		return `${m % 1 === 0 ? m : m.toFixed(1)}M`;
	}
	if (n >= 1000) {
		const k = n / 1000;
		return `${k % 1 === 0 ? k : k.toFixed(k < 10 ? 1 : 0)}K`;
	}
	return String(n);
};

export const getModelLimits = (model: any): ModelLimitsInfo | null => {
	const context =
		Number(model?.context_length ?? model?.contextLength ?? model?.info?.meta?.context_length ?? NaN) ||
		Number(model?.info?.params?.context_length ?? NaN);
	const maxOut = Number(
		model?.top_provider?.max_completion_tokens ??
			model?.top_provider?.maxOutputTokens ??
			model?.max_completion_tokens ??
			model?.info?.meta?.max_output_tokens ??
			model?.info?.params?.max_tokens ??
			NaN
	);

	const contextTokens = Number.isFinite(context) && context > 0 ? Math.round(context) : null;
	const maxOutputTokens = Number.isFinite(maxOut) && maxOut > 0 ? Math.round(maxOut) : null;

	if (contextTokens === null && maxOutputTokens === null) return null;

	const parts: string[] = [];
	if (contextTokens !== null) parts.push(`${formatTokens(contextTokens)} ctx`);
	if (maxOutputTokens !== null) parts.push(`${formatTokens(maxOutputTokens)} out`);

	const longParts: string[] = [];
	if (contextTokens !== null) {
		longParts.push(`Janela de contexto: ${contextTokens.toLocaleString('pt-PT')} tokens`);
	}
	if (maxOutputTokens !== null) {
		longParts.push(`Máx. saída: ${maxOutputTokens.toLocaleString('pt-PT')} tokens`);
	}
	longParts.push(`Imagens: máx. 30 MB (limite OpenRouter)`);

	return {
		contextTokens,
		maxOutputTokens,
		short: parts.join(' · '),
		long: longParts.join(' · ')
	};
};

const POPULAR_PATTERNS: { key: string; patterns: string[] }[] = [
	{ key: 'openai', patterns: ['openai', 'gpt-4', 'gpt-5', 'gpt-3.5', 'chatgpt', 'o1', 'o3', 'o4'] },
	{ key: 'anthropic', patterns: ['anthropic', 'claude'] },
	{ key: 'google', patterns: ['google', 'gemini', 'gemma'] },
	{ key: 'xai', patterns: ['xai', 'grok'] },
	{ key: 'meta', patterns: ['meta-llama', 'meta/', 'llama-3', 'llama-4'] },
	{ key: 'deepseek', patterns: ['deepseek'] },
	{ key: 'mistral', patterns: ['mistral', 'mixtral'] },
	{ key: 'qwen', patterns: ['qwen', 'alibaba'] },
	{ key: 'cohere', patterns: ['cohere', 'command-r'] },
	{ key: 'microsoft', patterns: ['microsoft', 'phi-', 'mai-'] }
];

const FREE_STORAGE_KEY = 'tugaai.recentModels';

const haystack = (item: any): string =>
	[
		item?.value ?? '',
		item?.label ?? '',
		item?.model?.id ?? '',
		item?.model?.name ?? '',
		(item?.model?.tags ?? [])
			.map((t: any) => (typeof t === 'string' ? t : (t?.name ?? '')))
			.join(' ')
	]
		.join(' ')
		.toLowerCase();

export const isFreeModel = (item: any): boolean => {
	const id = String(item?.model?.id ?? item?.value ?? '').toLowerCase();
	const label = String(item?.label ?? '').toLowerCase();
	const tags = (item?.model?.tags ?? [])
		.map((t: any) => String(typeof t === 'string' ? t : (t?.name ?? '')).toLowerCase())
		.join(' ');

	if (id.endsWith(':free') || id.includes(':free:') || label.includes('(free)')) {
		return true;
	}
	if (/\bfree\b/.test(tags) || /\bfree\b/.test(label)) {
		return true;
	}

	const promptPrice = Number(item?.model?.pricing?.prompt ?? item?.model?.pricing?.input ?? NaN);
	const completionPrice = Number(
		item?.model?.pricing?.completion ?? item?.model?.pricing?.output ?? NaN
	);
	if (
		(Number.isFinite(promptPrice) && promptPrice === 0) &&
		(Number.isFinite(completionPrice) && completionPrice === 0)
	) {
		return true;
	}

	return false;
};

export const getPopularBrand = (item: any): string | null => {
	const hay = haystack(item);
	for (const { key, patterns } of POPULAR_PATTERNS) {
		if (patterns.some((p) => hay.includes(p))) {
			return key;
		}
	}
	return null;
};

export const isPopularModel = (item: any): boolean => getPopularBrand(item) !== null;

export const getRecentModelIds = (): string[] => {
	try {
		const raw = localStorage.getItem(FREE_STORAGE_KEY);
		if (!raw) return [];
		const parsed = JSON.parse(raw);
		return Array.isArray(parsed) ? parsed.filter((x) => typeof x === 'string') : [];
	} catch {
		return [];
	}
};

export const rememberModelUsage = (modelId: string) => {
	if (!modelId) return;
	try {
		const prev = getRecentModelIds().filter((id) => id !== modelId);
		const next = [modelId, ...prev].slice(0, 24);
		localStorage.setItem(FREE_STORAGE_KEY, JSON.stringify(next));
	} catch {
		// ignore quota / private mode
	}
};

export const getCategoryKey = (
	item: any,
	pinnedIds: string[] = [],
	recentIds: string[] = []
): ModelCategoryKey => {
	const id = String(item?.model?.id ?? item?.value ?? '');
	if (pinnedIds.includes(id) || recentIds.includes(id)) {
		return 'used';
	}
	if (isFreeModel(item)) {
		return 'free';
	}
	if (isPopularModel(item)) {
		return 'popular';
	}
	return 'other';
};

export const matchesCategory = (
	item: any,
	category: string,
	pinnedIds: string[] = [],
	recentIds: string[] = []
): boolean => {
	if (!category) return true;
	if (category === 'free') return isFreeModel(item);
	if (category === 'popular') return isPopularModel(item);
	if (category === 'used') {
		const id = String(item?.model?.id ?? item?.value ?? '');
		return pinnedIds.includes(id) || recentIds.includes(id);
	}
	return getCategoryKey(item, pinnedIds, recentIds) === category;
};

export const sortModelsByCategory = (
	items: any[],
	pinnedIds: string[] = [],
	recentIds: string[] = []
): any[] => {
	const rank = (item: any) => {
		const key = getCategoryKey(item, pinnedIds, recentIds);
		const base = MODEL_CATEGORY_ORDER.indexOf(key);
		// Free popular models stay under Popular for discovery; free-only go to Free.
		return base;
	};
	return [...items].sort((a, b) => {
		const ra = rank(a);
		const rb = rank(b);
		if (ra !== rb) return ra - rb;
		return String(a?.label ?? a?.value ?? '').localeCompare(
			String(b?.label ?? b?.value ?? ''),
			'pt-PT',
			{ sensitivity: 'base' }
		);
	});
};

export type ModelSortKey = 'default' | 'used' | 'cheap' | 'expensive' | 'az' | 'za';

export const MODEL_SORT_KEYS: ModelSortKey[] = [
	'default',
	'used',
	'cheap',
	'expensive',
	'az',
	'za'
];

const sortName = (a: any, b: any): number =>
	String(a?.label ?? a?.value ?? '').localeCompare(String(b?.label ?? b?.value ?? ''), 'pt-PT', {
		sensitivity: 'base'
	});

/** Lower is cheaper. Unknown prices sort last (Infinity). */
const priceRank = (item: any): number => {
	const id = String(item?.model?.id ?? item?.value ?? '').toLowerCase();
	if (id.endsWith(':free') || id.includes(':free:')) return 0;

	const prompt = Number(item?.model?.pricing?.prompt ?? item?.model?.pricing?.input ?? NaN);
	const completion = Number(item?.model?.pricing?.completion ?? item?.model?.pricing?.output ?? NaN);
	const hasPrompt = Number.isFinite(prompt);
	const hasCompletion = Number.isFinite(completion);

	if (!hasPrompt && !hasCompletion) return Number.POSITIVE_INFINITY;
	if (hasPrompt && hasCompletion && prompt === 0 && completion === 0) return 0;

	const parts = [hasPrompt ? prompt : null, hasCompletion ? completion : null].filter(
		(v): v is number => v !== null
	);
	return parts.reduce((sum, v) => sum + v, 0) / parts.length;
};

const recentRank = (item: any, pinnedIds: string[], recentIds: string[]): number => {
	const id = String(item?.model?.id ?? item?.value ?? '');
	const ri = recentIds.indexOf(id);
	if (ri >= 0) return ri;
	if (pinnedIds.includes(id)) return recentIds.length + pinnedIds.indexOf(id);
	return Number.MAX_SAFE_INTEGER;
};

export const sortModelItems = (
	items: any[],
	sortKey: ModelSortKey | string = 'default',
	pinnedIds: string[] = [],
	recentIds: string[] = []
): any[] => {
	const list = [...items];

	switch (sortKey) {
		case 'az':
			return list.sort(sortName);
		case 'za':
			return list.sort((a, b) => sortName(b, a));
		case 'cheap':
			return list.sort((a, b) => {
				const pa = priceRank(a);
				const pb = priceRank(b);
				if (pa !== pb) return pa - pb;
				return sortName(a, b);
			});
		case 'expensive':
			return list.sort((a, b) => {
				const pa = priceRank(a);
				const pb = priceRank(b);
				if (pa !== pb) {
					// Unknown price (Infinity) always last, even when sorting expensive-first.
					if (pa === Number.POSITIVE_INFINITY) return 1;
					if (pb === Number.POSITIVE_INFINITY) return -1;
					return pb - pa;
				}
				return sortName(a, b);
			});
		case 'used':
			return list.sort((a, b) => {
				const ra = recentRank(a, pinnedIds, recentIds);
				const rb = recentRank(b, pinnedIds, recentIds);
				if (ra !== rb) return ra - rb;
				return sortName(a, b);
			});
		default:
			return sortModelsByCategory(list, pinnedIds, recentIds);
	}
};
