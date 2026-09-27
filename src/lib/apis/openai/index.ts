import { OPENAI_API_BASE_URL, WEBUI_API_BASE_URL, WEBUI_BASE_URL } from '$lib/constants';
import { isRateLimitError } from '$lib/utils/errorMessages';
import { toast } from 'svelte-sonner';
import { get } from 'svelte/store';
import i18n from '$lib/i18n';

const RETRY_TOAST_ID = 'openai-chat-completion-retry';

const translate = (key: string): string => {
	try {
		return get(i18n)?.t(key) ?? key;
	} catch {
		return key;
	}
};

export const getErrorMessage = (err: any, fallback = 'Server connection failed') => {
	const detail = err?.detail;
	if (typeof detail === 'string') return detail;

	return (
		detail?.error?.message ??
		detail?.message ??
		err?.error?.message ??
		err?.message ??
		(typeof err === 'string' ? err : fallback)
	);
};

export const getOpenAIConfig = async (token: string = '') => {
	let error = null;

	const res = await fetch(`${OPENAI_API_BASE_URL}/config`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			error = getErrorMessage(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

type OpenAIConfig = {
	ENABLE_OPENAI_API: boolean;
	OPENAI_API_BASE_URLS: string[];
	OPENAI_API_KEYS: string[];
	OPENAI_API_CONFIGS: object;
};

export const updateOpenAIConfig = async (token: string = '', config: OpenAIConfig) => {
	let error = null;

	const res = await fetch(`${OPENAI_API_BASE_URL}/config/update`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		},
		body: JSON.stringify({
			...config
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			error = getErrorMessage(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getOpenAIModelsDirect = async (url: string, key: string) => {
	let error = null;

	const res = await fetch(`${url}/models`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(key && { authorization: `Bearer ${key}` })
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = `OpenAI: ${err?.error?.message ?? 'Network Problem'}`;
			return [];
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getOpenAIModels = async (token: string, urlIdx?: number) => {
	let error = null;

	const res = await fetch(
		`${OPENAI_API_BASE_URL}/models${typeof urlIdx === 'number' ? `/${urlIdx}` : ''}`,
		{
			method: 'GET',
			headers: {
				Accept: 'application/json',
				'Content-Type': 'application/json',
				...(token && { authorization: `Bearer ${token}` })
			}
		}
	)
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = `OpenAI: ${err?.error?.message ?? 'Network Problem'}`;
			return [];
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getProviderModelCatalog = async (token: string, urlIdx: number) => {
	let error = null;

	const res = await fetch(`${OPENAI_API_BASE_URL}/models/${urlIdx}/catalog`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token && { authorization: `Bearer ${token}` })
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = getErrorMessage(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const downloadProviderModel = async (
	token: string,
	urlIdx: number,
	model: string,
	signal?: AbortSignal
) => {
	let error = null;

	const res = await fetch(`${OPENAI_API_BASE_URL}/models/${urlIdx}/download`, {
		signal,
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: JSON.stringify({ model })
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = getErrorMessage(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getProviderModelDownloadStatus = async (
	token: string,
	urlIdx: number,
	jobId: string,
	signal?: AbortSignal
) => {
	let error = null;

	const res = await fetch(
		`${OPENAI_API_BASE_URL}/models/${urlIdx}/download/status/${encodeURIComponent(jobId)}`,
		{
			signal,
			method: 'GET',
			headers: {
				Accept: 'application/json',
				'Content-Type': 'application/json',
				Authorization: `Bearer ${token}`
			}
		}
	)
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = getErrorMessage(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const loadProviderModel = async (token: string, urlIdx: number, model: string) => {
	let error = null;

	const res = await fetch(`${OPENAI_API_BASE_URL}/models/${urlIdx}/load`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: JSON.stringify({ model })
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = getErrorMessage(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const unloadProviderModel = async (
	token: string,
	urlIdx: number,
	model: string,
	instanceId?: string
) => {
	let error = null;

	const res = await fetch(`${OPENAI_API_BASE_URL}/models/${urlIdx}/unload`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: JSON.stringify({ model, ...(instanceId ? { instance_id: instanceId } : {}) })
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = getErrorMessage(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteProviderModel = async (token: string, urlIdx: number, model: string) => {
	let error = null;

	const res = await fetch(
		`${OPENAI_API_BASE_URL}/models/${urlIdx}?${new URLSearchParams({ model })}`,
		{
			method: 'DELETE',
			headers: {
				Accept: 'application/json',
				'Content-Type': 'application/json',
				Authorization: `Bearer ${token}`
			}
		}
	)
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = getErrorMessage(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const verifyOpenAIConnection = async (
	token: string = '',
	connection: Record<string, any> = {},
	direct: boolean = false
) => {
	const { url, key, config } = connection;
	if (!url) {
		throw 'OpenAI: URL is required';
	}

	let error = null;
	let res = null;

	if (direct) {
		res = await fetch(`${url}/models`, {
			method: 'GET',
			headers: {
				Accept: 'application/json',
				Authorization: `Bearer ${key}`,
				'Content-Type': 'application/json'
			}
		})
			.then(async (res) => {
				if (!res.ok) throw await res.json();
				return res.json();
			})
			.catch((err) => {
				error = `OpenAI: ${err?.error?.message ?? 'Network Problem'}`;
				return [];
			});

		if (error) {
			throw error;
		}
	} else {
		res = await fetch(`${OPENAI_API_BASE_URL}/verify`, {
			method: 'POST',
			headers: {
				Accept: 'application/json',
				Authorization: `Bearer ${token}`,
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({
				url,
				key,
				config
			})
		})
			.then(async (res) => {
				if (!res.ok) throw await res.json();
				return res.json();
			})
			.catch((err) => {
				error = `OpenAI: ${err?.error?.message ?? 'Network Problem'}`;
				return [];
			});

		if (error) {
			throw error;
		}
	}

	return res;
};

export const chatCompletion = async (
	token: string = '',
	body: object,
	url: string = `${WEBUI_BASE_URL}/api`
): Promise<[Response | null, AbortController]> => {
	const controller = new AbortController();
	let error = null;

	const res = await fetch(`${url}/chat/completions`, {
		signal: controller.signal,
		method: 'POST',
		headers: {
			Authorization: `Bearer ${token}`,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify(body)
	}).catch((err) => {
		console.error(err);
		error = err;
		return null;
	});

	if (error) {
		throw error;
	}

	return [res, controller];
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export const generateOpenAIChatCompletion = async (
	token: string = '',
	body: object,
	url: string = `${WEBUI_BASE_URL}/api`
) => {
	// Upstream free/shared pools return 429 or ResourceExhausted (e.g. NVIDIA 16/16
	// workers) — surface a friendly message after retrying.
	// The backend already replays HTTP 429 up to RATE_LIMIT_MAX_ATTEMPTS times
	// (see backend/open_webui/routers/openai.py); this call often arrives with
	// HTTP 200 + {error:{code:429}} once those attempts are exhausted. Keep the
	// client-side retry small (a single extra attempt) so the user is not left
	// waiting through two stacked retry chains.
	const maxAttempts = 2;
	const delaysMs = [3000];
	let lastError: any = null;

	// Surface the backoff to the user: without it, a silent 3s wait looks like
	// a frozen app. The toast auto-dismisses with the delay and is also removed
	// explicitly on success or on the final failure.
	const showRetrying = (delayMs: number, attempt: number) => {
		toast.loading(translate('Retrying…'), {
			id: RETRY_TOAST_ID,
			duration: delayMs + 1500
		});
		console.warn(
			`Rate limited (429) — retrying in ${Math.round(delayMs / 1000)}s (attempt ${attempt}/${maxAttempts})`
		);
	};

	for (let attempt = 1; attempt <= maxAttempts; attempt++) {
		let fetchError: any = null;
		let payload: any = null;

		payload = await fetch(`${url}/chat/completions`, {
			method: 'POST',
			headers: {
				Authorization: `Bearer ${token}`,
				'Content-Type': 'application/json'
			},
			credentials: 'include',
			body: JSON.stringify(body)
		})
			.then(async (res) => {
				const json = await res.json().catch(() => null);
				if (!res.ok) {
					throw json ?? { error: { message: `HTTP ${res.status}` } };
				}
				return json;
			})
			.catch((err) => {
				fetchError = err;
				return null;
			});

		const rateLimited =
			isRateLimitError(fetchError) ||
			isRateLimitError((fetchError as any)?.error) ||
			isRateLimitError(payload?.error) ||
			payload?.error?.code === 429;

		if (fetchError) {
			lastError = fetchError;
			if (rateLimited && attempt < maxAttempts) {
				const delay = delaysMs[attempt - 1] ?? 5000;
				showRetrying(delay, attempt + 1);
				await sleep(delay);
				continue;
			}
			toast.dismiss(RETRY_TOAST_ID);
			// Preserve full object so callers can detect code 429 / rate-limit text.
			throw fetchError;
		}

		// HTTP 200 but body carries a provider error (common Open WebUI pattern).
		if (payload?.error) {
			lastError = payload;
			if (rateLimited && attempt < maxAttempts) {
				const delay = delaysMs[attempt - 1] ?? 5000;
				showRetrying(delay, attempt + 1);
				await sleep(delay);
				continue;
			}
			toast.dismiss(RETRY_TOAST_ID);
			return payload; // Chat.svelte: res.error → handleOpenAIError
		}

		toast.dismiss(RETRY_TOAST_ID);
		return payload;
	}

	toast.dismiss(RETRY_TOAST_ID);
	throw lastError;
};

export const synthesizeOpenAISpeech = async (
	token: string = '',
	speaker: string = 'alloy',
	text: string = '',
	model: string = 'tts-1'
) => {
	let error = null;

	const res = await fetch(`${OPENAI_API_BASE_URL}/audio/speech`, {
		method: 'POST',
		headers: {
			Authorization: `Bearer ${token}`,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify({
			model: model,
			input: text,
			voice: speaker
		})
	}).catch((err) => {
		console.error(err);
		error = err;
		return null;
	});

	if (error) {
		throw error;
	}

	return res;
};
