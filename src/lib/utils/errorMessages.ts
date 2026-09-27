////////////////////////////////////////
// Friendly error messages
//
// Providers (OpenRouter, NVIDIA, Google, ...) answer with raw JSON payloads
// full of internals (codes, metadata, user ids).  These helpers recognise the
// common failure patterns and return an i18n *key* (the English source
// string) so every surface — toast or in-chat error bubble — can show a
// human message instead of the raw payload.
////////////////////////////////////////

const toText = (raw: unknown): string => {
	if (raw == null) return '';
	if (typeof raw === 'string') return raw;

	try {
		return JSON.stringify(raw) ?? String(raw);
	} catch {
		return String(raw);
	}
};

export const isRateLimitError = (raw: unknown): boolean => {
	if (raw == null) return false;
	if (typeof raw === 'number' && raw === 429) return true;
	if (typeof raw === 'string' && /^\s*429\s*$/.test(raw)) return true;

	if (typeof raw === 'object') {
		const anyRaw = raw as Record<string, any>;
		if (
			anyRaw?.code === 429 ||
			anyRaw?.status === 429 ||
			anyRaw?.statusCode === 429 ||
			anyRaw?.error?.code === 429 ||
			anyRaw?.detail?.code === 429
		) {
			return true;
		}
	}

	const text = toText(raw);
	return (
		/\b429\b/.test(text) ||
		/rate[-_ ]?limit/i.test(text) ||
		/temporarily rate-limited/i.test(text) ||
		/too many requests/i.test(text) ||
		/upstream_provider_shared_pool/i.test(text) ||
		// NVIDIA vLLM: "ResourceExhausted: Worker local total request limit reached (16/16)"
		/ResourceExhausted/i.test(text) ||
		/request limit reached/i.test(text) ||
		(/\b\d+\/\d+\)/.test(text) && /worker|concurrent|request/i.test(text))
	);
};

// i18n keys (English source strings) — callers run them through `t()`.
export const FRIENDLY_ERROR_KEYS = {
	disconnectedDuringImageProcessing:
		'A ligação foi perdida durante o processamento das imagens. Envie a mensagem outra vez — as imagens já foram pré-processadas.',
	providerBusy:
		'The provider is at full capacity right now. Wait a few seconds and try again, or pick another model.',
	rateLimited:
		'This free model is temporarily rate-limited. Wait a minute and try again, pick another free model, or add credits / your own key on OpenRouter.',
	modelUnavailable:
		'The model did not respond. Please try again in a moment, or pick another model.',
	unknown: 'Uh-oh! There was an issue with the response.'
} as const;

const isGenericProviderFailure = (text: string): boolean =>
	/Provider returned error/i.test(text) ||
	/Internal server error/i.test(text) ||
	/Service unavailable/i.test(text) ||
	/Bad gateway/i.test(text) ||
	/\bHTTP (5\d{2}|408|403|401)\b/.test(text) ||
	/"code"\s*:\s*(5\d{2}|408|403|401)\b/.test(text);

/**
 * Returns an i18n key with a friendly message for the recognised error, or an
 * empty string when the payload is unknown (callers then fall back to the raw
 * content).
 */
export const getFriendlyErrorMessage = (raw: unknown): string => {
	if (raw == null) return '';

	const text = toText(raw);
	if (!text) return '';

	if (/Client session disconnected/i.test(text)) {
		return FRIENDLY_ERROR_KEYS.disconnectedDuringImageProcessing;
	}

	if (isRateLimitError(raw)) {
		if (/ResourceExhausted|request limit reached/i.test(text)) {
			return FRIENDLY_ERROR_KEYS.providerBusy;
		}
		return FRIENDLY_ERROR_KEYS.rateLimited;
	}

	if (isGenericProviderFailure(text)) {
		return FRIENDLY_ERROR_KEYS.modelUnavailable;
	}

	return '';
};
