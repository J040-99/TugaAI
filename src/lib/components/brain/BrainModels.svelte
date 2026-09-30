<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { models } from '$lib/stores';
	import { getUserSettings, updateUserSettings } from '$lib/apis/users';
	import { toast } from 'svelte-sonner';

	const i18n = getContext('i18n');

	let organizeModel = '';
	let visionModel = '';
	let savingModels = false;

	const loadBrainSettings = async () => {
		try {
			const settings = await getUserSettings(localStorage.token);
			const brain = settings?.brain ?? {};
			organizeModel = brain.organize_model ?? '';
			visionModel = brain.vision_model ?? '';
		} catch {
			/* sem preferências guardadas — fica o default do servidor */
		}
	};

	const saveBrainSettings = async () => {
		savingModels = true;
		try {
			const current = (await getUserSettings(localStorage.token)) ?? {};
			await updateUserSettings(localStorage.token, {
				...current,
				brain: {
					...(current.brain ?? {}),
					organize_model: organizeModel,
					vision_model: visionModel
				}
			});
			toast.success($i18n.t('Saved'));
		} catch {
			toast.error($i18n.t('Uh-oh! There was an issue with the response.'));
		} finally {
			savingModels = false;
		}
	};

	onMount(loadBrainSettings);
</script>

<section
	class="mb-6 rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
>
	<h2 class="text-sm font-semibold text-gray-900 dark:text-white">
		{$i18n.t('Brain models')}
	</h2>
	<p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
		{$i18n.t('Choose which model the brain uses for each task.')}
	</p>

	<div class="mt-3 grid gap-3 sm:grid-cols-2">
		<label class="block text-xs text-gray-500 dark:text-gray-400">
			{$i18n.t('File organisation')}
			<select
				bind:value={organizeModel}
				class="focus-ring mt-1 w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 outline-hidden dark:border-gray-800 dark:bg-gray-950 dark:text-gray-100"
			>
				<option value="">{$i18n.t('Server default')}</option>
				{#each $models as m (m.id)}
					<option value={m.id}>{m.id}</option>
				{/each}
			</select>
		</label>

		<label class="block text-xs text-gray-500 dark:text-gray-400">
			{$i18n.t('Images and PDFs')}
			<select
				bind:value={visionModel}
				class="focus-ring mt-1 w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 outline-hidden dark:border-gray-800 dark:bg-gray-950 dark:text-gray-100"
			>
				<option value="">{$i18n.t('Server default')}</option>
				{#each $models as m (m.id)}
					<option value={m.id}>{m.id}</option>
				{/each}
			</select>
		</label>
	</div>

	<div class="mt-3 flex flex-wrap items-center gap-3">
		<button
			class="rounded-xl bg-gray-900 px-3.5 py-1.5 text-sm font-medium text-white transition hover:bg-gray-800 disabled:opacity-60 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
			disabled={savingModels}
			on:click={saveBrainSettings}
		>
			{$i18n.t('Save')}
		</button>
		<span class="text-xs text-gray-400 dark:text-gray-500">
			{$i18n.t('Reflection uses the server default model.')}
		</span>
	</div>
</section>
