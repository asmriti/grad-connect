"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import {
  fetchFilters,
  matchResume,
  PAGE_SIZE,
  relevanceLabel,
  type Filters,
  type MatchResponse,
} from "@/lib/api";

export default function MatchPage() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");
  const [university, setUniversity] = useState("");
  const [country, setCountry] = useState("");
  const [filters, setFilters] = useState<Filters>({
    universities: [],
    countries: [],
  });
  const [response, setResponse] = useState<MatchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchFilters()
      .then(setFilters)
      .catch(() => {
        /* filters are a convenience; matching still works without them */
      });
  }, []);

  async function runMatch(page: number) {
    const file = fileRef.current?.files?.[0] ?? null;
    if (!file && !text.trim()) {
      setError("Choose a resume file or paste its text first.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await matchResume({ file, text: text.trim() }, university, country, page);
      setResponse(res);
      if (page > 1) window.scrollTo({ top: 0 });
    } catch (e) {
      setResponse(null);
      setError(
        e instanceof Error && e.message && !e.message.startsWith("Request failed")
          ? e.message
          : "Matching is unavailable. Check that the backend is running, then try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    runMatch(1);
  }

  const totalPages = response ? Math.ceil(response.total / PAGE_SIZE) : 0;
  const page = response?.page ?? 1;
  const nothingMatched =
    response !== null && (response.chunks_used === 0 || response.total === 0);

  return (
    <main>
      <form className="search-form" onSubmit={onSubmit}>
        <p className="match-intro">
          Upload your resume — or paste it — to find professors whose pages
          read closest to your experience and projects. The file is matched in
          memory and never stored.
        </p>

        <div className="field">
          <label htmlFor="resume-file">Resume file (.pdf, .docx, .txt, .md)</label>
          <input
            id="resume-file"
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.txt,.md"
            className="file-input"
          />
        </div>

        <div className="field">
          <label htmlFor="resume-text">Or paste your resume</label>
          <textarea
            id="resume-text"
            className="resume-textarea"
            rows={7}
            placeholder="Paste your projects and experience here… (ignored if a file is chosen)"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </div>

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
            {loading ? "Matching…" : "Match"}
          </button>
        </div>
      </form>

      {error && <p className="error-note">{error}</p>}

      {nothingMatched && !error && (
        <p className="status-line">
          None of the resume was close enough to a professor page to show a
          match. Try pasting just your projects or research experience section
          — focused text matches better than a full CV.
        </p>
      )}

      {response !== null && !error && response.total > 0 && (
        <>
          <p className="status-line">
            {response.total === 1
              ? "1 professor matched"
              : `${response.total} professors matched`}
            {response.filename ? ` against ${response.filename}` : ""}
            {response.truncated
              ? ` — only the first ${response.chunks_used} sections of a long resume were used`
              : ""}
            {totalPages > 1
              ? ` — showing ${(page - 1) * PAGE_SIZE + 1}–${
                  (page - 1) * PAGE_SIZE + response.results.length
                }`
              : ""}
          </p>

          {response.results.map((result) => (
            <article className="result-card" key={result.professor.id}>
              <div className="result-head">
                <h2>
                  <Link href={`/professors/${result.professor.id}`}>
                    {result.professor.name}
                  </Link>
                </h2>
                <span className="relevance">{relevanceLabel(result.similarity)}</span>
              </div>
              <p className="result-meta">
                {result.professor.affiliation}
                {result.professor.country ? ` · ${result.professor.country}` : ""}
              </p>

              {result.matches.map((match, i) => (
                <div className="match-pair" key={i}>
                  <p className="resume-quote">
                    <span className="resume-quote-label">From your resume</span>
                    “{match.resume_excerpt}”
                  </p>
                  <figure className="evidence">
                    <blockquote>“{shorten(match.text, 320)}”</blockquote>
                    <cite>
                      {match.heading ? `${match.heading} — ` : ""}
                      <a href={match.url} target="_blank" rel="noreferrer">
                        {match.page_title || match.url}
                      </a>
                    </cite>
                  </figure>
                </div>
              ))}

              <div className="result-actions">
                <Link href={`/professors/${result.professor.id}`}>View professor</Link>
                <a href={result.professor.homepage} target="_blank" rel="noreferrer">
                  Homepage ↗
                </a>
              </div>
            </article>
          ))}

          {totalPages > 1 && (
            <nav className="pagination" aria-label="Match result pages">
              <button
                type="button"
                onClick={() => runMatch(page - 1)}
                disabled={page <= 1 || loading}
              >
                ← Previous
              </button>
              <span className="pagination-status">
                Page {Math.min(page, totalPages)} of {totalPages}
              </span>
              <button
                type="button"
                onClick={() => runMatch(page + 1)}
                disabled={page >= totalPages || loading}
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

function shorten(text: string, max: number): string {
  const flat = text.replace(/\s+/g, " ").trim();
  if (flat.length <= max) return flat;
  return flat.slice(0, max).replace(/\s+\S*$/, "") + "…";
}
