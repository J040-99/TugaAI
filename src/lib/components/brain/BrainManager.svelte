<script lang="ts">
	import { getContext } from 'svelte';
	import { WEBUI_BASE_URL } from '$lib/constants';
	import { toast } from 'svelte-sonner';

	const i18n = getContext('i18n');

	const authHeaders = () => ({ Authorization: `Bearer ${localStorage.token}` });

	/** Página actual de cartões carregados (controlada pela página). */
	export let cards: any[] = [];
	/** chave (hash/id) → nº de cópias idênticas entre os cartões visíveis. */
	export let dupCounts: Map<string, number> = new Map();
	/** Chamado depois de qualquer operação que mude a lista (a página recarrega). */
	export let onChanged: () => void = () => {};

	let uploading = false;
	let fileInput: HTMLInputElement;
	let editingId = '';
	let editTitle = '';
	let editSummary = '';

	const onUploadFiles = async (event: Event) => {
		const input = event.target as HTMLInputElement;
		if (!input.files || input.files.length === 0) return;
		uploading = true;
		try {
			for (const file of Array.from(input.files)) {
				const form = new FormData();
				form.append('file', file);
				const res = await fetch(`${WEBUI_BASE_URL}/api/v1/files/?process=true`, {
					method: 'POST',
					headers: authHeaders(),
					credentials: 'include',
					body: form
				});
				if (!res.ok) throw new Error('upload failed');
			}
			toast.success($i18n.t('Uploaded'));
			onChanged();
		} catch {
			toast.error($i18n.t('Uh-oh! There was an issue with the response.'));
		} finally {
			uploading = false;
			input.value = '';
		}
	};

	const deleteFile = async (id: string, name: string) => {
		if (!confirm(`${$i18n.t('Delete')}: ${name}`)) return;
		try {
			const res = await fetch(`${WEBUI_BASE_URL}/api/v1/files/${id}`, {
				method: 'DELETE',
				headers: authHeaders(),
				credentials: 'include'
			});
			if (!res.ok) throw new Error('delete failed');
			toast.success($i18n.t('Deleted'));
			onChanged();
		} catch {
			toast.error($i18n.t('Uh-oh! There was an issue with the response.'));
		}
	};

	const reorganiseFile = async (id: string) => {
		try {
			const res = await fetch(`${WEBUI_BASE_URL}/api/v1/files/brain/${id}/reorganize`, {
				method: 'POST',
				headers: authHeaders(),
				credentials: 'include'
			});
			if (!res.ok) throw new Error('reorganize failed');
			toast.success($i18n.t('Saved'));
			onChanged();
		} catch {
			toast.error($i18n.t('Uh-oh! There was an issue with the response.'));
		}
	};

	const startEditCard = (card: any) => {
		editingId = card.id;
		editTitle = card.brain?.title ?? '';
		editSummary = card.brain?.summary ?? '';
	};

	const saveCard = async (id: string) => {
		try {
			const res = await fetch(`${WEBUI_BASE_URL}/api/v1/files/brain/${id}/card`, {
				method: 'PUT',
				headers: { ...authHeaders(), 'Content-Type': 'application/json' },
				credentials: 'include',
				body: JSON.stringify({ title: editTitle, summary: editSummary })
			});
			if (!res.ok) throw new Error('save failed');
			toast.success($i18n.t('Saved'));
			editingId = '';
			onChanged();
		} catch {
			toast.error($i18n.t('Uh-oh! There was an issue with the response.'));
		}
	};

	const cleanupDuplicates = async () => {
		if (!confirm($i18n.t('Clean duplicates'))) return;
		try {
			const res = await fetch(`${WEBUI_BASE_URL}/api/v1/files/brain/cleanup-duplicates`, {
				method: 'POST',
				headers: authHeaders(),
				credentials: 'include'
			});
			if (!res.ok) throw new Error('cleanup failed');
			const data = await res.json();
			toast.success(`${$i18n.t('Deleted')}: ${data.deleted}`);
			onChanged();
		} catch {
			toast.error($i18n.t('Uh-oh! There was an issue with the response.'));
		}
	};
</script>

<!-- Gestor de informação: adicionar, editar, reorganizar, apagar -->
<section
	class="mb-6 rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
>
	<div>
		<h2 class="text-sm font-semibold text-gray-900 dark:text-white">
			{$i18n.t('Information manager')}
		</h2>
		<div class="mt-2 flex flex-wrap gap-2">
			<button
				class="shrink-0 whitespace-nowrap rounded-xl border border-amber-200 px-2.5 py-1.5 text-xs font-medium text-amber-700 transition hover:bg-amber-50 disabled:opacity-60 dark:border-amber-500/30 dark:text-amber-300"
				on:click={cleanupDuplicates}
			>
				{$i18n.t('Remove duplicates')}
			</button>
			<button
				class="shrink-0 whitespace-nowrap rounded-xl bg-gray-900 px-2.5 py-1.5 text-xs font-medium text-white transition hover:bg-gray-800 disabled:opacity-60 dark:bg-white dark:text-gray-900"
				disabled={uploading}
				on:click={() => fileInput?.click()}
			>
				{uploading ? '…' : `+ ${$i18n.t('Add Files')}`}
			</button>
		</div>
		<input bind:this={fileInput} type="file" multiple class="hidden" on:change={onUploadFiles} />
	</div>

	<div class="mt-3 space-y-2">
		{#each cards as card (card.id)}
			<div class="rounded-xl border border-gray-100 p-2.5 dark:border-gray-800">
				<div class="flex flex-wrap items-center gap-2">
					<span class="block w-full truncate text-sm text-gray-800 dark:text-gray-100">
						{card.filename}
					</span>
					{#if (dupCounts.get(card.hash ?? card.id) ?? 0) > 1}
						<span
							class="shrink-0 whitespace-nowrap rounded bg-amber-100 px-1.5 py-0.5 text-[0.625rem] font-medium text-amber-700 dark:bg-amber-500/15 dark:text-amber-300"
						>
							{$i18n.t('Duplicate')} ×{dupCounts.get(card.hash ?? card.id)}
						</span>
					{/if}
				</div>

				<div class="mt-1.5 flex flex-wrap gap-1.5">
					<button
						class="whitespace-nowrap rounded-lg bg-gray-100 px-2 py-1 text-xs text-gray-600 transition hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
						on:click={() => reorganiseFile(card.id)}
					>
						{$i18n.t('Reorganise')}
					</button>
					<button
						class="whitespace-nowrap rounded-lg bg-gray-100 px-2 py-1 text-xs text-gray-600 transition hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
						on:click={() => startEditCard(card)}
					>
						{$i18n.t('Edit')}
					</button>
					<button
						class="whitespace-nowrap rounded-lg bg-red-50 px-2 py-1 text-xs text-red-600 transition hover:bg-red-100 dark:bg-red-500/10 dark:text-red-400"
						on:click={() => deleteFile(card.id, card.filename)}
					>
						{$i18n.t('Delete')}
					</button>
				</div>

				{#if editingId === card.id}
					<div class="mt-2 space-y-2">
						<input
							bind:value={editTitle}
							class="focus-ring w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-950"
							placeholder={$i18n.t('Title')}
						/>
						<textarea
							bind:value={editSummary}
							rows="2"
							class="focus-ring w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-950"
							placeholder={$i18n.t('Summary')}
						></textarea>
						<div class="flex gap-2">
							<button
								class="rounded-lg bg-gray-900 px-2.5 py-1 text-xs font-medium text-white disabled:opacity-60 dark:bg-white dark:text-gray-900"
								on:click={() => saveCard(card.id)}
							>
								{$i18n.t('Save')}
							</button>
							<button
								class="rounded-lg bg-gray-100 px-2.5 py-1 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-300"
								on:click={() => (editingId = '')}
							>
								{$i18n.t('Cancel')}
							</button>
						</div>
					</div>
				{/if}
			</div>
		{/each}

		{#if cards.length === 0}
			<p class="text-xs text-gray-400 dark:text-gray-500">
				{$i18n.t('No memories yet')}
			</p>
		{/if}
	</div>
</section>
