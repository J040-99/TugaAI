import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ManagerHost from './ManagerHost.svelte';

const cards = [
	{ id: 'f1', filename: 'resumo.pdf', hash: 'h1', brain: { title: 'Título um', summary: 'Um' } },
	{ id: 'f2', filename: 'copia.pdf', hash: 'h1', brain: { title: 'Título dois', summary: '' } }
];

beforeEach(() => {
	vi.stubGlobal(
		'confirm',
		vi.fn(() => true)
	);
	vi.stubGlobal(
		'fetch',
		vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ deleted: 0 }) }) as Response)
	);
});

describe('BrainManager', () => {
	it('lista os ficheiros e marca duplicados', () => {
		render(ManagerHost, { props: { cards, dupCounts: new Map([['h1', 2]]) } });
		expect(screen.getByText('resumo.pdf')).toBeTruthy();
		expect(screen.getByText('copia.pdf')).toBeTruthy();
		// badge "Duplicate ×2" nos DOIS ficheiros do par idêntico
		expect(screen.getAllByText(/Duplicate/)).toHaveLength(2);
		expect(screen.getAllByText(/×2/)).toHaveLength(2);
	});

	it('abre o editor de cartão e guarda com onChanged', async () => {
		const changed = vi.fn();
		render(ManagerHost, { props: { cards, dupCounts: new Map(), changed } });

		await fireEvent.click(screen.getAllByText('Edit')[0]);
		const title = (await screen.findByPlaceholderText('Title')) as HTMLInputElement;
		expect(title.value).toBe('Título um');

		await fireEvent.input(title, { target: { value: 'Título editado' } });
		await fireEvent.click(screen.getByText('Save'));
		await waitFor(() => expect(changed).toHaveBeenCalled());
	});

	it('apaga com confirmação e notifica a página', async () => {
		const changed = vi.fn();
		render(ManagerHost, { props: { cards, dupCounts: new Map(), changed } });

		await fireEvent.click(screen.getAllByText('Delete')[0]);
		await waitFor(() => expect(changed).toHaveBeenCalled());
		expect(globalThis.confirm).toHaveBeenCalled();
	});
});
