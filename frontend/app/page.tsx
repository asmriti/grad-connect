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

export default function SearchPage() {
  // useSearchParams needs a Suspense boundary during prerendering.
  return (
    <Suspense>
      <SearchPageInner />
    </Suspense>
  );
}

function SearchPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // The URL is the source of truth for an executed search, so navigating to a
  // professor page and back (or reloading, or sharing the link) restores the
  // form, the results, and the current page.
  const activeQuery = searchParams.get("query") ?? "";
  const activeUniversity = searchParams.get("university") ?? "";
  const activeCountry = searchParams.get("country") ?? "";
  const activePage = Math.max(1, Number(searchParams.get("page")) || 1);

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

  // Run (or re-run) the search whenever the URL's search state changes —
  // on submit, on page change, on back/forward, and on loading a shared link.
  useEffect(() => {
    // Keep the form in sync when the URL changes via history navigation.
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
    searchProfessors(activeQuery.trim(), activeUniversity, activeCountry, activePage)
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
  }, [activeQuery, activeUniversity, activeCountry, activePage]);

  function pushSearch(page: number) {
    const trimmed = query.trim();
    if (!trimmed) return;
    const params = new URLSearchParams({ query: trimmed });
    if (university) params.set("university", university);
    if (country) params.set("country", country);
    if (page > 1) params.set("page", String(page));
    // push (not replace) so back/forward moves between searches and pages too.
    router.push(`/?${params.toString()}`);
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    pushSearch(1); // a new search always starts at the first page
  }

  function goToPage(page: number) {
    pushSearch(page);
    window.scrollTo({ top: 0 });
  }

  const totalPages = response ? Math.ceil(response.total / PAGE_SIZE) : 0;
  const results = response?.results ?? null;

  return (
    <main>
      <form className="search-form" onSubmit={onSubmit}>
       
        <div className="search-controls">
          <div className="field">
            <label htmlFor="university">University</label>
            <select
              id="university"
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
          </div>
          <div className="field">
            <label htmlFor="country">Country</label>
            <select
              id="country"
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
          </div>
          <button className="search-button" type="submit" disabled={loading}>
            {loading ? "Searching…" : "Search"}
          </button>
        </div>
      </form>

      {error && <p className="error-note">{error}</p>}

      {response !== null && results !== null && !error && (
        <>
          <p className="status-line">
            {response.total === 0
              ? "No professor's pages discuss this topic closely enough to show. Try different wording, or clear the filters."
              : response.total === 1
                ? "1 professor found"
                : `${response.total} professors found` +
                  (totalPages > 1
                    ? ` — showing ${(activePage - 1) * PAGE_SIZE + 1}–${
                        (activePage - 1) * PAGE_SIZE + results.length
                      }`
                    : "")}
          </p>

          {results.length === 0 && response.total > 0 && (
            <p className="empty-note">
              This page is past the end of the results.
            </p>
          )}

          {results.map((result) => (
            <ProfessorCard key={result.professor.id} result={result} />
          ))}

          {totalPages > 1 && (
            <nav className="pagination" aria-label="Search result pages">
              <button
                type="button"
                onClick={() => goToPage(activePage - 1)}
                disabled={activePage <= 1 || loading}
              >
                ← Previous
              </button>
              <span className="pagination-status">
                Page {Math.min(activePage, totalPages)} of {totalPages}
              </span>
              <button
                type="button"
                onClick={() => goToPage(activePage + 1)}
                disabled={activePage >= totalPages || loading}
              >
                Next →
              </button>
            </nav>
          )}
        </>
      )}
    </main>
  );
}
