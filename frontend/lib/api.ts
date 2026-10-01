const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Professor {
  id: number;
  name: string;
  affiliation: string;
  country: string | null;
  homepage: string;
  scholar_id: string | null;
  orcid: string | null;
}

export interface Evidence {
  text: string;
  url: string;
  page_title: string | null;
  heading: string | null;
}

export interface SearchResult {
  professor: Professor;
  similarity: number;
  evidence: Evidence[];
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  total: number;
  page: number;
  page_size: number;
}

export interface Filters {
  universities: string[];
  countries: string[];
}

export interface DocumentInfo {
  id: number;
  url: string;
  title: string | null;
  page_type: string | null;
  http_status: number | null;
}

export interface Chunk {
  id: number;
  text: string;
  url: string;
  page_title: string | null;
  heading: string | null;
}

export interface ProfessorDetail {
  professor: Professor;
  documents: DocumentInfo[];
  chunks: Chunk[];
}

export interface MatchPair {
  resume_excerpt: string;
  text: string;
  url: string;
  page_title: string | null;
  heading: string | null;
}

export interface MatchResult {
  professor: Professor;
  similarity: number;
  matches: MatchPair[];
}

export interface MatchResponse {
  filename: string | null;
  chunks_used: number;
  truncated: boolean;
  results: MatchResult[];
  total: number;
  page: number;
  page_size: number;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) {
    throw new Error(`Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export const PAGE_SIZE = 10;

export function searchProfessors(
  query: string,
  university: string,
  country: string,
  page = 1,
  minSimilarity?: number,
): Promise<SearchResponse> {
  const params = new URLSearchParams({
    query,
    page: String(page),
    limit: String(PAGE_SIZE),
  });
  if (university) params.set("university", university);
  if (country) params.set("country", country);
  if (minSimilarity != null) params.set("min_similarity", String(minSimilarity));
  return get<SearchResponse>(`/api/search?${params.toString()}`);
}

/** POST a resume (file or pasted text) for matching. Nothing is stored
 * server-side; the resume only exists for the duration of the request. */
export async function matchResume(
  input: { file: File | null; text: string },
  university: string,
  country: string,
  page = 1,
  minSimilarity?: number,
): Promise<MatchResponse> {
  const form = new FormData();
  if (input.file) {
    form.set("file", input.file);
  } else {
    form.set("text", input.text);
  }
  if (university) form.set("university", university);
  if (country) form.set("country", country);
  if (minSimilarity != null) form.set("min_similarity", String(minSimilarity));
  form.set("page", String(page));
  form.set("limit", String(PAGE_SIZE));

  const res = await fetch(`${API_URL}/api/match`, { method: "POST", body: form });
  if (!res.ok) {
    let detail = "";
    try {
      detail = (await res.json()).detail ?? "";
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<MatchResponse>;
}

export function fetchFilters(): Promise<Filters> {
  return get<Filters>("/api/filters");
}

export function fetchProfessor(id: string): Promise<ProfessorDetail> {
  return get<ProfessorDetail>(`/api/professors/${id}`);
}

/** Raw cosine similarity → a label a person can act on. */
export function relevanceLabel(similarity: number): string {
  if (similarity >= 0.72) return "Strong match";
  if (similarity >= 0.62) return "Good match";
  return "Possible match";
}
