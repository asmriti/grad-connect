export interface SavedProfessor {
  id: number;
  name: string;
  affiliation: string;
  country: string | null;
  homepage: string;
}

const KEY = "grad-connect-saved";
export const SAVED_EVENT = "grad-connect-saved";

export function readSaved(): SavedProfessor[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as SavedProfessor[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeSaved(items: SavedProfessor[]) {
  window.localStorage.setItem(KEY, JSON.stringify(items));
  window.dispatchEvent(new Event(SAVED_EVENT));
}

export function toggleSaved(professor: SavedProfessor): SavedProfessor[] {
  const current = readSaved();
  const next = current.some((item) => item.id === professor.id)
    ? current.filter((item) => item.id !== professor.id)
    : [professor, ...current];
  writeSaved(next);
  return next;
}
