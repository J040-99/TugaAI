<script lang="ts">
	import { setContext } from 'svelte';
	import { readable } from 'svelte/store';
	import BrainManager from '../BrainManager.svelte';

	export let cards: any[] = [];
	export let dupCounts: Map<string, number> = new Map();
	export let changed: () => void = () => {};

	setContext('i18n', readable({ t: (key: string) => key, language: 'en', languages: [] }));
</script>

<BrainManager {cards} {dupCounts} onChanged={changed} />
