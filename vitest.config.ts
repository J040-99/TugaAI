import { fileURLToPath } from 'node:url';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';

// Configuração própria do Vitest para os testes de UI (jsdom) — não herda o
// vite.config.ts do SvelteKit para os testes correrem leves e isolados.
export default defineConfig({
	plugins: [svelte()],
	// Espelha o vite.config.ts (injetado no build real) — $lib/constants usa-os.
	define: {
		APP_VERSION: JSON.stringify(process.env.npm_package_version || '0.0.0-test'),
		APP_BUILD_HASH: JSON.stringify(process.env.APP_BUILD_HASH || 'test-build')
	},
	resolve: {
		// Em testes, o vitest corre em modo node — sem browser as condições,
		// o svelte resolve a runtime de servidor e o mount() rebenta.
		conditions: ['browser'],
		alias: {
			$lib: fileURLToPath(new URL('./src/lib', import.meta.url))
		}
	},
	test: {
		environment: 'jsdom',
		globals: true,
		include: ['src/**/*.{test,spec}.{js,ts}'],
		setupFiles: ['./vitest.setup.ts']
	}
});
