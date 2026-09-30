<script lang="ts">
	import { onMount } from 'svelte';
	import { WEBUI_BASE_URL } from '$lib/constants';

	/** Ficheiro .excalidraw — mostra o desenho como SVG (sem dependências). */
	export let fileId = '';

	let svgMarkup = '';

	const color = (value: unknown, fallback: string): string =>
		typeof value === 'string' && /^#[0-9a-fA-F]{3,8}$/.test(value) ? value : fallback;

	const esc = (value: string): string =>
		value
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;');

	const num = (value: unknown, fallback = 0): number => {
		const parsed = typeof value === 'number' ? value : Number(value);
		return Number.isFinite(parsed) ? parsed : fallback;
	};

	function pointsPath(element: any): string {
		const points = Array.isArray(element.points) ? element.points : [];
		if (points.length === 0) return '';
		const ox = num(element.x);
		const oy = num(element.y);
		return points
			.map(
				([px, py]: [number, number], index: number) =>
					`${index === 0 ? 'M' : 'L'} ${(ox + num(px)).toFixed(1)} ${(oy + num(py)).toFixed(1)}`
			)
			.join(' ');
	}

	/** Mini-renderer: elementos do Excalidraw → SVG estático. */
	function render(data: any): string {
		if (!data || typeof data !== 'object') return '';
		const supported = [
			'rectangle',
			'ellipse',
			'diamond',
			'line',
			'arrow',
			'freedraw',
			'text',
			'image'
		];
		const elements: any[] = (Array.isArray(data.elements) ? data.elements : []).filter(
			(e: any) => e && !e.isDeleted && supported.includes(e.type)
		);
		if (elements.length === 0) return '';

		let minX = Infinity;
		let minY = Infinity;
		let maxX = -Infinity;
		let maxY = -Infinity;
		for (const e of elements) {
			minX = Math.min(minX, num(e.x));
			minY = Math.min(minY, num(e.y));
			maxX = Math.max(maxX, num(e.x) + Math.max(num(e.width), 0));
			maxY = Math.max(maxY, num(e.y) + Math.max(num(e.height), 0));
		}
		const pad = 16;
		const viewBox = `${minX - pad} ${minY - pad} ${maxX - minX + pad * 2} ${maxY - minY + pad * 2}`;

		const body = elements
			.map((e) => {
				const x = num(e.x);
				const y = num(e.y);
				const w = Math.max(num(e.width), 0);
				const h = Math.max(num(e.height), 0);
				const stroke = color(e.strokeColor, '#1e1e1e');
				const fill =
					!e.backgroundColor || e.backgroundColor === 'transparent'
						? 'none'
						: color(e.backgroundColor, 'none');
				const sw = Math.max(num(e.strokeWidth, 1), 1);
				const cx = x + w / 2;
				const cy = y + h / 2;
				const angle = num(e.angle, 0);
				const rotate = angle
					? ` transform="rotate(${((angle * 180) / Math.PI).toFixed(2)} ${cx.toFixed(1)} ${cy.toFixed(1)})"`
					: '';

				switch (e.type) {
					case 'rectangle':
						return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="8" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"${rotate} />`;
					case 'ellipse':
						return `<ellipse cx="${cx}" cy="${cy}" rx="${w / 2}" ry="${h / 2}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"${rotate} />`;
					case 'diamond':
						return `<polygon points="${cx},${y} ${x + w},${cy} ${cx},${y + h} ${x},${cy}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"${rotate} />`;
					case 'line':
					case 'arrow': {
						const d = pointsPath(e) || `M ${x} ${y} L ${x + w} ${y + h}`;
						const marker = e.type === 'arrow' ? ' marker-end="url(#ea)"' : '';
						return `<path d="${d}" fill="none" stroke="${stroke}" stroke-width="${sw}" stroke-linecap="round"${marker}${rotate} />`;
					}
					case 'freedraw': {
						const d = pointsPath(e);
						return d
							? `<path d="${d}" fill="none" stroke="${stroke}" stroke-width="${Math.max(sw, 2)}" stroke-linecap="round" stroke-linejoin="round"${rotate} />`
							: '';
					}
					case 'text': {
						const size = Math.max(num(e.fontSize, 16), 6);
						const lines = String(e.text ?? '').split('\n');
						const spans = lines
							.map(
								(line: string, i: number) =>
									`<tspan x="${x}" dy="${i === 0 ? size : size * 1.25}">${esc(line)}</tspan>`
							)
							.join('');
						return `<text y="${(y + size * 0.95).toFixed(1)}" fill="${stroke}" font-size="${size}" font-family="Inter, system-ui, sans-serif"${rotate}>${spans}</text>`;
					}
					case 'image':
						return `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="none" stroke="${stroke}" stroke-dasharray="6 4" /><text x="${cx}" y="${cy}" text-anchor="middle" font-size="12" fill="${stroke}">imagem</text>`;
					default:
						return '';
				}
			})
			.join('');

		return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" class="max-h-72 w-full"><defs><marker id="ea" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="${strokeMarker}" /></marker></defs>${body}</svg>`;
	}

	const strokeMarker = '#1e1e1e';

	onMount(async () => {
		if (!fileId) return;
		try {
			const res = await fetch(`${WEBUI_BASE_URL}/api/v1/files/${fileId}/content`, {
				headers: { Authorization: `Bearer ${localStorage.token}` },
				credentials: 'include'
			});
			if (!res.ok) return;
			const data = await res.json();
			svgMarkup = render(data);
		} catch {
			/* não é JSON/excalidraw — não mostra pré-visualização */
		}
	});
</script>

{#if svgMarkup}
	<div
		class="mt-2 overflow-hidden rounded-lg border border-gray-100 bg-white p-2 dark:border-gray-800 dark:bg-gray-950"
	>
		{@html svgMarkup}
	</div>
{/if}
