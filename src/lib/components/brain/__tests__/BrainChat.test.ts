import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ChatHost from './ChatHost.svelte';

// Dependências pesadas/externas isoladas:
vi.mock('$lib/components/chat/Messages/Markdown.svelte', () => import('./MarkdownStub.svelte'));
vi.mock('svelte-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

type Call = { url: string; method?: string };
const calls: Call[] = [];

const jsonResponse = (data: unknown, ok = true) =>
	({ ok, status: ok ? 200 : 500, json: async () => data }) as Response;

beforeEach(() => {
	calls.length = 0;
	localStorage.setItem('token', 'token-de-teste');
	vi.stubGlobal(
		'fetch',
		vi.fn(async (url: string, init?: RequestInit) => {
			const method = init?.method ?? 'GET';
			calls.push({ url: String(url), method });
			if (String(url).endsWith('/brain/ask')) {
				return jsonResponse({ answer: 'resposta do cérebro', sources: ['doc.pdf'] });
			}
			if (String(url).includes('/brain/chat') && method === 'PUT') {
				return jsonResponse({ status: true, count: 1 });
			}
			if (String(url).includes('/brain/chat') && method === 'DELETE') {
				return jsonResponse({ status: true });
			}
			if (String(url).includes('/brain/chat')) {
				return jsonResponse({
					items: [{ q: 'pergunta antiga', a: 'resposta antiga', sources: [] }]
				});
			}
			return jsonResponse({});
		})
	);
});

describe('BrainChat', () => {
	it('carrega o histórico do servidor ao montar', async () => {
		render(ChatHost);
		await waitFor(() => expect(screen.getByText('pergunta antiga')).toBeTruthy());
		expect(
			calls.some((c) => c.url.includes('/api/v1/files/brain/chat') && c.method === 'GET')
		).toBe(true);
	});

	it('desactiva o envio sem pergunta e envia com Enter/submissão', async () => {
		render(ChatHost);
		const button = screen.getByRole('button', { name: 'Send' }) as HTMLButtonElement;
		expect(button.disabled).toBe(true);

		const input = screen.getByPlaceholderText('Ask anything about your knowledge...');
		await fireEvent.input(input, { target: { value: 'O que sei sobre a 3ª Fase?' } });
		expect((screen.getByRole('button', { name: 'Send' }) as HTMLButtonElement).disabled).toBe(
			false
		);

		await fireEvent.submit(input.closest('form') as HTMLFormElement);
		await waitFor(() =>
			expect(
				screen
					.getAllByTestId('markdown-stub')
					.some((el) => (el.textContent ?? '').includes('resposta do cérebro'))
			).toBe(true)
		);
		// a pergunta aparece na conversa
		expect(screen.getByText('O que sei sobre a 3ª Fase?')).toBeTruthy();
		// e o histórico foi guardado no servidor (PUT)
		await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true));
	});

	it('limpa a conversa e apaga o histórico no servidor', async () => {
		render(ChatHost);
		await waitFor(() => expect(screen.getByText('pergunta antiga')).toBeTruthy());

		await fireEvent.click(screen.getByText('Clear conversation'));
		await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true));
		expect(screen.queryByText('pergunta antiga')).toBeNull();
	});
});
