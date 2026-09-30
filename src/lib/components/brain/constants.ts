// Constantes partilhadas pela interface do Modo Cérebro.

export const CATEGORIES = ['memory', 'person', 'place', 'document', 'other'];

export const CATEGORY_STYLES: Record<string, string> = {
	memory: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
	person: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300',
	place: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
	document: 'bg-gray-100 text-gray-700 dark:bg-gray-500/15 dark:text-gray-300',
	other: 'bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300'
};

export const ENTITY_STYLES: Record<string, string> = {
	person: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300',
	place: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
	topic: 'bg-gray-100 text-gray-700 dark:bg-gray-500/15 dark:text-gray-300'
};
