<script lang="ts">
	import { setContext } from 'svelte';
	import { readable } from 'svelte/store';
	import BrainChat from '../BrainChat.svelte';

	// Fornece o contexto i18n (a página real usa a store global) com chaves
	// literais — os testes procuram pelos textos ingleses das chaves.
	setContext('i18n', readable({ t: (key: string) => key, language: 'en', languages: [] }));
</script>

<BrainChat />
