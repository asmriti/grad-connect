"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import ProfessorCard from "@/components/ProfessorCard";
import {
  fetchFilters,
  PAGE_SIZE,
  searchProfessors,
  type Filters,
  type SearchResponse,
} from "@/lib/api";

const SUGGESTIONS = [
  "accepting PhD students 2027",
  "undergraduate research",
  "funded master's positions",
];

const AUDIENCE = [
  { id: "phd", label: "PhD students", query: "PhD students" },
  { id: "masters", label: "Master's students", query: "master's students" },
  { id: "ug", label: "Undergraduates", query: "undergraduate students" },
] as const;

const STRONG_FLOOR = 0.72;

export default function SearchPage() {
  return (
    <Suspense>
      <SearchPageInner />
    </Suspense>
  );
}

function SearchPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const activeQuery = searchParams.get("query") ?? "";
  const activeUniversity = searchParams.get("university") ?? "";
  const activeCountry = searchParams.get("country") ?? "";
  const activePage = Math.max(1, Number(searchParams.get("page")) || 1);
  const activeFocus = parseFocus(searchParams.get("focus"));
  const activeStrong = searchParams.get("strength") === "strong";

  const [query, setQuery] = useState(activeQuery);
  const [university, setUniversity] = useState(activeUniversity);
  const [country, setCountry] = useState(activeCountry);
  const [filters, setFilters] = useState<Filters>({
    universities: [],
    countries: [],
  });
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchFilters()
      .then(setFilters)
      .catch(() => {
        /* filters are a convenience; search still works without them */
      });
  }, []);

  useEffect(() => {
    setQuery(activeQuery);
    setUniversity(activeUniversity);
    setCountry(activeCountry);

    if (!activeQuery.trim()) {
      setResponse(null);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    const apiQuery = expandQuery(activeQuery, activeFocus);
    searchProfessors(
      apiQuery,
      activeUniversity,
      activeCountry,
      activePage,
      activeStrong ? STRONG_FLOOR : undefined,
    )
      .then((res) => {
        if (!cancelled) setResponse(res);
      })
      .catch(() => {
        if (!cancelled)
          setError(
            "Search is unavailable. Check that the backend is running, then try again.",
          );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    activeQuery,
    activeUniversity,
    activeCountry,
    activePage,
    activeFocus.join(","),
    activeStrong,
  ]);

  function navigate(next: {
    query?: string;
    page?: number;
    focus?: string[];
    strong?: boolean;
    university?: string;
    country?: string;
  }) {
    const q = (next.query ?? activeQuery).trim();
    if (!q) return;
    const params = new URLSearchParams({ query: q });
    const uni = next.university ?? activeUniversity;
    const ctry = next.country ?? activeCountry;
    const focus = next.focus ?? activeFocus;
    const strong = next.strong ?? activeStrong;
    const page = next.page ?? 1;
    if (uni) params.set("university", uni);
    if (ctry) params.set("country", ctry);
    if (focus.length) params.set("focus", focus.join(","));
    if (strong) params.set("strength", "strong");
    if (page > 1) params.set("page", String(page));
    router.push(`/?${params.toString()}`);
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    navigate({ query, university, country, page: 1 });
  }

  function toggleFocus(id: string) {
    const focus = activeFocus.includes(id)
      ? activeFocus.filter((item) => item !== id)
      : [...activeFocus, id];
    navigate({ focus, page: 1 });
  }

  const filtersOn = activeFocus.length > 0 || activeStrong;
  const totalPages = response ? Math.ceil(response.total / PAGE_SIZE) : 0;
  const results = response?.results ?? null;
  const terms = expandQuery(activeQuery, activeFocus).split(/\s+/);

  return (
    <main>
      <section className="hero">
        <h1>Find the professor behind the research you care about</h1>
        <p>
          Search by topic. Every result quotes the professor&apos;s own pages, so
          you can see exactly why they matched.
        </p>
      </section>

      <form className="search-bar" role="search" onSubmit={onSubmit}>
        <div className="search-bar-query">
          <SearchIcon />
          <input
            id="query"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="looking for students"
            aria-label="Research topic"
          />
        </div>
        <label className="bar-select">
          <span>University</span>
          <select
            id="university"
            aria-label="University"
            value={university}
            onChange={(e) => setUniversity(e.target.value)}
          >
            <option value="">All universities</option>
            {filters.universities.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </select>
        </label>
        <label className="bar-select">
          <span>Country</span>
          <select
            id="country"
            aria-label="Country"
            value={country}
            onChange={(e) => setCountry(e.target.value)}
          >
            <option value="">All countries</option>
            {filters.countries.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <button className="search-button" type="submit" disabled={loading}>
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      <div className="try-row">
        <span>Try</span>
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            className="chip"
            onClick={() => {
              setQuery(suggestion);
              navigate({ query: suggestion, university, country, page: 1 });
            }}
          >
            {suggestion}
          </button>
        ))}
      </div>

      {error && <p className="error-note">{error}</p>}

      {activeQuery.trim() && (
        <div className="workspace">
          <aside className="refine" aria-label="Refine results">
            <div className="refine-head">
              <span>Refine</span>
              <button
                type="button"
                onClick={() =>
                  navigate({ focus: [], strong: false, page: 1 })
                }
                disabled={!filtersOn}
              >
                Clear all
              </button>
            </div>

            <fieldset>
              <legend>Looking for</legend>
              {AUDIENCE.map((item) => (
                <label key={item.id}>
                  <input
                    type="checkbox"
                    checked={activeFocus.includes(item.id)}
                    onChange={() => toggleFocus(item.id)}
                  />
                  {item.label}
                </label>
              ))}
            </fieldset>

            <fieldset>
              <legend>Match strength</legend>
              <label>
                <input
                  type="radio"
                  name="strength"
                  checked={!activeStrong}
                  onChange={() => navigate({ strong: false, page: 1 })}
                />
                Any
              </label>
              <label>
                <input
                  type="radio"
                  name="strength"
                  checked={activeStrong}
                  onChange={() => navigate({ strong: true, page: 1 })}
                />
                Strong only
              </label>
            </fieldset>
          </aside>

          <div>
            {response !== null && results !== null && !error && (
              <div className="results-toolbar">
                <p>
                  {response.total === 0
                    ? "No professor's pages discuss this topic closely enough to show."
                    : response.total === 1
                      ? "1 professor"
                      : `${response.total} professors`}
                  {activeUniversity ? ` at ${activeUniversity}` : ""}
                  {response.total > 0 &&
                    ` · showing ${(activePage - 1) * PAGE_SIZE + 1}–${
                      (activePage - 1) * PAGE_SIZE + results.length
                    }`}
                </p>
                <label className="sort">
                  Sort by
                  <select aria-label="Sort by" defaultValue="best">
                    <option value="best">Best match</option>
                  </select>
                </label>
              </div>
            )}

            {results?.map((result) => (
              <ProfessorCard
                key={result.professor.id}
                result={result}
                terms={terms}
              />
            ))}

            {totalPages > 1 && (
              <nav className="pagination" aria-label="Search result pages">
                {pageWindow(activePage, totalPages).map((page) => (
                  <button
                    key={page}
                    type="button"
                    className={page === activePage ? "page-current" : undefined}
                    aria-current={page === activePage ? "page" : undefined}
                    onClick={() => {
                      navigate({ page });
                      window.scrollTo({ top: 0 });
                    }}
                    disabled={loading}
                  >
                    {page}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => {
                    navigate({ page: activePage + 1 });
                    window.scrollTo({ top: 0 });
                  }}
                  disabled={activePage >= totalPages || loading}
                >
                  Next →
                </button>
              </nav>
            )}
          </div>
        </div>
      )}
    </main>
  );
}

function parseFocus(value: string | null): string[] {
  const allowed = new Set(AUDIENCE.map((item) => item.id));
  if (!value) return [];
  return value.split(",").filter((id) => allowed.has(id as (typeof AUDIENCE)[number]["id"]));
}

function expandQuery(query: string, focus: string[]): string {
  const extra = AUDIENCE.filter((item) => focus.includes(item.id)).map((item) => item.query);
  return [query.trim(), ...extra].filter(Boolean).join(" ");
}

function pageWindow(current: number, total: number): number[] {
  const start = Math.max(1, Math.min(current - 2, total - 4));
  const end = Math.min(total, start + 4);
  const pages: number[] = [];
  for (let page = Math.max(1, end - 4); page <= end; page += 1) pages.push(page);
  return pages;
}

function SearchIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="7" cy="7" r="4.25" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <path d="M10.4 10.4 13.2 13.2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}
