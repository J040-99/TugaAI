export type ModelModalityCapability =
	| 'vision'
	| 'audio_in'
	| 'video_in'
	| 'text'
	| 'image_generation'
	| 'audio_out'
	| 'video_out'
	| 'web_search'
	| 'file_upload'
	| 'code_interpreter'
	| 'terminal';

export type ModelCapabilityBadge = {
	key: ModelModalityCapability;
	/** i18n key or literal label for tooltip */
	labelKey: string;
};

const normalizeList = (value: unknown): string[] => {
	if (Array.isArray(value)) {
		return value.map((v) => String(v).toLowerCase().trim()).filter(Boolean);
	}
	if (typeof value === 'string') {
		return value
			.split(/[,/+\s]+/)
			.map((v) => v.toLowerCase().trim())
			.filter(Boolean);
	}
	return [];
};

const hasIn = (list: string[], ...needles: string[]) =>
	needles.some((n) => list.includes(n) || list.some((item) => item.includes(n)));

/**
 * Resolve what a model can accept (input) and produce (output).
 * Sources: OpenRouter architecture.modalities, Open WebUI workspace capabilities, tags.
 */
export const getModelCapabilities = (model: any): Record<ModelModalityCapability, boolean> => {
	const caps = model?.info?.meta?.capabilities ?? model?.capabilities ?? {};
	const arch = model?.architecture ?? model?.arch ?? {};
	const tags = (model?.tags ?? [])
		.map((t: any) => String(typeof t === 'string' ? t : (t?.name ?? '')).toLowerCase())
		.join(' ');

	const input =
		normalizeList(arch.input_modalities ?? arch.inputModalities).length > 0
			? normalizeList(arch.input_modalities ?? arch.inputModalities)
			: normalizeList(arch.modality?.split('->')?.[0] ?? arch.modality);

	const output =
		normalizeList(arch.output_modalities ?? arch.outputModalities).length > 0
			? normalizeList(arch.output_modalities ?? arch.outputModalities)
			: normalizeList(arch.modality?.split('->')?.[1] ?? '');

	const supported = normalizeList(model?.supported_modalities ?? model?.modalities);

	const inSet = input.length ? input : supported;
	const outSet = output.length ? output : supported;

	const vision =
		caps.vision === true ||
		(caps.vision !== false && (hasIn(inSet, 'image', 'vision', 'img') || /\bvision\b|\bimage\b/.test(tags)));

	const audioIn =
		(hasIn(inSet, 'audio', 'speech', 'voice') || /\baudio\b|\bspeech\b/.test(tags)) &&
		caps.audio_input !== false;

	const videoIn =
		hasIn(inSet, 'video') || /\bvideo\b/.test(tags);

	const idLower = String(model?.id ?? '').toLowerCase();

	const imageGenByOutput = hasIn(outSet, 'image', 'img');
	const imageGenByHint =
		/\bimage[-_ ]?gen|\bdall-e|\bstable[-_ ]?diffusion|\bflux\b|\bimagen\b/.test(idLower);

	// Prefer explicit workspace flag; otherwise output modality "image" on non-vision chat models
	const imageGeneration =
		caps.image_generation === true
			? true
			: caps.image_generation === false
				? false
				: imageGenByOutput && !vision
					? true
					: imageGenByHint;

	const audioOut =
		hasIn(outSet, 'audio', 'speech', 'tts') ||
		/\btts\b|\btext[-_ ]?to[-_ ]?speech\b/.test(String(model?.id ?? '').toLowerCase());

	const videoOut = hasIn(outSet, 'video');

	const webSearch =
		caps.web_search === true ||
		(caps.web_search !== false && /\bweb[-_ ]?search\b|\bsearch\b/.test(tags)) ||
		/\bsearch\b|\bperplexity\b|\bferrum\b/.test(String(model?.id ?? '').toLowerCase());

	const fileUpload =
		caps.file_upload === true ||
		(caps.file_upload !== false && (vision || hasIn(inSet, 'file', 'document', 'pdf')));

	const codeInterpreter = caps.code_interpreter === true;
	const terminal = caps.terminal === true;

	// Explicit false from workspace capabilities wins for known flags
	return {
		text: hasIn(inSet, 'text') || inSet.length === 0,
		vision: caps.vision === false ? false : vision,
		audio_in: caps.audio_input === false ? false : audioIn,
		video_in: caps.video_input === false ? false : videoIn,
		image_generation: imageGeneration,
		audio_out: caps.audio_output === false ? false : audioOut,
		video_out: caps.video_output === false ? false : videoOut,
		web_search: caps.web_search === false ? false : webSearch,
		file_upload: caps.file_upload === false ? false : fileUpload,
		code_interpreter: caps.code_interpreter === false ? false : codeInterpreter,
		terminal: caps.terminal === false ? false : terminal
	};
};

/** Badges to show in the model selector (only true capabilities). */
export const getModelCapabilityBadges = (model: any): ModelCapabilityBadge[] => {
	const c = getModelCapabilities(model);
	const badges: ModelCapabilityBadge[] = [];

	if (c.vision) badges.push({ key: 'vision', labelKey: 'models.capability.vision' });
	if (c.audio_in) badges.push({ key: 'audio_in', labelKey: 'models.capability.audio_in' });
	if (c.video_in) badges.push({ key: 'video_in', labelKey: 'models.capability.video_in' });
	if (c.image_generation) badges.push({ key: 'image_generation', labelKey: 'models.capability.image_generation' });
	if (c.audio_out) badges.push({ key: 'audio_out', labelKey: 'models.capability.audio_out' });
	if (c.video_out) badges.push({ key: 'video_out', labelKey: 'models.capability.video_out' });
	if (c.web_search) badges.push({ key: 'web_search', labelKey: 'models.capability.web_search' });
	if (c.code_interpreter) badges.push({ key: 'code_interpreter', labelKey: 'models.capability.code_interpreter' });
	if (c.terminal) badges.push({ key: 'terminal', labelKey: 'models.capability.terminal' });

	return badges;
};

/** Human-readable summary for tooltips: "Aceita: imagens, áudio · Gera: imagens" */
export const describeModelCapabilities = (model: any, t: (key: string) => string): string => {
	const c = getModelCapabilities(model);
	const accepts: string[] = [];
	const produces: string[] = [];

	if (c.vision) accepts.push(t('models.capability.vision'));
	if (c.audio_in) accepts.push(t('models.capability.audio_in'));
	if (c.video_in) accepts.push(t('models.capability.video_in'));
	if (c.file_upload) accepts.push(t('models.capability.file_upload'));
	if (c.web_search) accepts.push(t('models.capability.web_search'));

	if (c.image_generation) produces.push(t('models.capability.image_generation'));
	if (c.audio_out) produces.push(t('models.capability.audio_out'));
	if (c.video_out) produces.push(t('models.capability.video_out'));

	const parts: string[] = [];
	if (accepts.length) parts.push(`${t('models.capability.accepts')}: ${accepts.join(', ')}`);
	if (produces.length) parts.push(`${t('models.capability.produces')}: ${produces.join(', ')}`);
	if (c.code_interpreter) parts.push(t('models.capability.code_interpreter'));
	if (c.terminal) parts.push(t('models.capability.terminal'));

	return parts.join(' · ');
};
