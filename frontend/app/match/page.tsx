"use client";

import Link from "next/link";
import { DragEvent, FormEvent, useEffect, useRef, useState } from "react";
import {
  fetchFilters,
  matchResume,
  PAGE_SIZE,
  relevanceLabel,
  type Filters,
  type MatchResponse,
  type MatchResult,
} from "@/lib/api";
import { readSaved, SAVED_EVENT, toggleSaved } from "@/lib/saved";

const STRONG_FLOOR = 0.72;
const ACCEPT = ".pdf,.docx,.txt,.md";
const OPENINGS =
  /looking for|recruiting|accepting|seeking|join the group|openings|prospective students/i;

export default function MatchPage() {
  const fileRef = useRef<HTMLInputElement>(null);
  const topicsTouched = useRef(false);
  const [mode, setMode] = useState<"file" | "text">("file");
  const [file, setFile] = useState<File | null>(null);
  const [readOk, setReadOk] = useState(false);
  const [text, setText] = useState("");
  const [university, setUniversity] = useState("");
  const [country, setCountry] = useState("");
  const [filters, setFilters] = useState<Filters>({ universities: [], countries: [] });
  const [topics, setTopics] = useState<string[]>([]);
  const [addingTopic, setAddingTopic] = useState(false);
  const [draftTopic, setDraftTopic] = useState("");
  const [strongOnly, setStrongOnly] = useState(false);
  const [openingsOnly, setOpeningsOnly] = useState(false);
  const [response, setResponse] = useState<MatchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => {
    fetchFilters()
      .then(setFilters)
      .catch(() => {
        /* filters are a convenience; matching still works without them */
      });
  }, []);

  function takeFile(next: File | null) {
    setFile(next);
    setReadOk(false);
    setMode("file");
    if (fileRef.current) fileRef.current.value = "";
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragOver(false);
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) takeFile(dropped);
  }

  async function runMatch(page: number, strong = strongOnly) {
    const useFile = mode === "file";
    if (useFile && !file) {
      setError("Choose a resume file or switch to paste.");
      return;
    }
    if (!useFile && !text.trim()) {
      setError("Paste your resume, or switch to upload.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await matchResume(
        useFile ? { file, text: "" } : { file: null, text: text.trim() },
        university,
        country,
        page,
        strong ? STRONG_FLOOR : undefined,
      );
      setResponse(res);
      if (useFile) setReadOk(true);
      if (!topicsTouched.current) {
        const source = useFile
          ? res.results.flatMap((result) => result.matches.map((match) => match.resume_excerpt)).join("\n")
          : text;
        setTopics(topicsFromText(source));
      }
      if (page > 1) window.scrollTo({ top: 0 });
    } catch (e) {
      setResponse(null);
      setReadOk(false);
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

  function addTopic() {
    const next = draftTopic.trim();
    if (!next || topics.some((topic) => topic.toLowerCase() === next.toLowerCase())) {
      setDraftTopic("");
      setAddingTopic(false);
      return;
    }
    topicsTouched.current = true;
    setTopics([...topics, next]);
    setDraftTopic("");
    setAddingTopic(false);
  }

  const page = response?.page ?? 1;
  const totalPages = response ? Math.ceil(response.total / PAGE_SIZE) : 0;
  const visible = (response?.results ?? []).filter(
    (result) => !openingsOnly || result.matches.some((match) => OPENINGS.test(match.text)),
  );
  const nothingMatched =
    response !== null && (response.chunks_used === 0 || response.total === 0);
  const filtersOn = strongOnly || openingsOnly;
  const label = response?.filename || "your resume";

  return (
    <main>
      <div className="match-hero">
        <section className="hero">
          <h1>Match your resume to professors</h1>
          <p>
            We compare your projects and experience with what professors write on
            their own pages, then show you the lines that connect.
          </p>
          <p className="memory-note">Matched in memory. Your resume is never stored.</p>
        </section>

        <form
          className={`resume-card${dragOver ? " drag-over" : ""}`}
          onSubmit={onSubmit}
          onDragOver={(event) => {
            event.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
        >
          <div className="resume-tabs" role="tablist" aria-label="Resume input">
            <button
              type="button"
              role="tab"
              aria-selected={mode === "file"}
              onClick={() => setMode("file")}
            >
              Upload file
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "text"}
              onClick={() => setMode("text")}
            >
              Paste text
            </button>
          </div>

          {mode === "file" ? (
            file ? (
              <div className="file-row">
                <span className="file-badge">{fileKind(file.name)}</span>
                <div>
                  <strong>{file.name}</strong>
                  <span className={readOk ? "read-ok" : "read-pending"}>
                    {readOk ? "Read successfully" : "Ready to match"}
                  </span>
                </div>
                <button type="button" className="text-btn" onClick={() => fileRef.current?.click()}>
                  Replace
                </button>
                <button type="button" className="icon-x" aria-label="Remove file" onClick={() => takeFile(null)}>
                  ×
                </button>
              </div>
            ) : (
              <button type="button" className="dropzone" onClick={() => fileRef.current?.click()}>
                Choose a PDF, DOCX, TXT, or MD file, or drop it here.
              </button>
            )
          ) : (
            <textarea
              className="resume-textarea"
              rows={5}
              placeholder="Paste your projects and experience here…"
              value={text}
              aria-label="Paste your resume"
              onChange={(e) => setText(e.target.value)}
            />
          )}

          <p className="file-hint">
            PDF, DOCX, TXT or MD. Drop a new file anywhere on this card to replace it.
          </p>

          <div className="match-bar">
            <label className="bar-select">
              <span>University</span>
              <select
                aria-label="University"
                value={university}
                onChange={(e) => setUniversity(e.target.value)}
              >
                <option value="">All universities</option>
                {filters.universities.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label className="bar-select">
              <span>Country</span>
              <select aria-label="Country" value={country} onChange={(e) => setCountry(e.target.value)}>
                <option value="">All countries</option>
                {filters.countries.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <button className="search-button" type="submit" disabled={loading}>
              {loading ? "Matching…" : "Find matches"}
            </button>
          </div>

          <input
            ref={fileRef}
            type="file"
            accept={ACCEPT}
            hidden
            aria-label="Resume file"
            onChange={(event) => {
              const next = event.target.files?.[0] ?? null;
              if (next) takeFile(next);
            }}
          />
        </form>
      </div>

      {(topics.length > 0 || addingTopic) && (
        <div className="topic-row">
          <span className="topic-label">Matching on</span>
          {topics.map((topic) => (
            <button
              key={topic}
              type="button"
              className="topic-chip"
              onClick={() => {
                topicsTouched.current = true;
                setTopics(topics.filter((item) => item !== topic));
              }}
            >
              {topic}
              <span aria-hidden="true">×</span>
              <span className="sr-only">Remove {topic}</span>
            </button>
          ))}
          {addingTopic ? (
            <input
              className="topic-input"
              aria-label="Add a topic"
              value={draftTopic}
              autoFocus
              onChange={(e) => setDraftTopic(e.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  addTopic();
                }
                if (event.key === "Escape") setAddingTopic(false);
              }}
              onBlur={addTopic}
            />
          ) : (
            <button type="button" className="topic-add" onClick={() => setAddingTopic(true)}>
              + Add topic
            </button>
          )}
          <span className="topic-note">
            Pulled from your resume. Remove any that don&apos;t reflect what you want to study.
          </span>
        </div>
      )}

      {error && <p className="error-note">{error}</p>}

      {nothingMatched && !error && (
        <p className="status-line">
          None of the resume was close enough to a professor page to show a match. Try
          pasting just your projects or research experience — focused text matches better
          than a full CV.
        </p>
      )}

      {response !== null && !error && response.total > 0 && (
        <div className="workspace">
          <aside className="refine" aria-label="Refine results">
            <div className="refine-head">
              <span>Refine</span>
              <button
                type="button"
                disabled={!filtersOn}
                onClick={() => {
                  setOpeningsOnly(false);
                  if (strongOnly) {
                    setStrongOnly(false);
                    runMatch(1, false);
                  }
                }}
              >
                Clear all
              </button>
            </div>
            <fieldset>
              <legend>Match strength</legend>
              <label>
                <input
                  type="radio"
                  name="match-strength"
                  checked={!strongOnly}
                  onChange={() => {
                    setStrongOnly(false);
                    runMatch(1, false);
                  }}
                />
                Any
              </label>
              <label>
                <input
                  type="radio"
                  name="match-strength"
                  checked={strongOnly}
                  onChange={() => {
                    setStrongOnly(true);
                    runMatch(1, true);
                  }}
                />
                Strong only
              </label>
            </fieldset>
            <fieldset>
              <legend>Recruiting</legend>
              <label>
                <input
                  type="checkbox"
                  checked={openingsOnly}
                  onChange={() => setOpeningsOnly(!openingsOnly)}
                />
                Mentions open positions
              </label>
            </fieldset>
          </aside>

          <div>
            <div className="results-toolbar">
              <p>
                {response.total === 1 ? "1 professor" : `${response.total} professors`} matched
                to {label}
                {visible.length > 0
                  ? ` · showing ${(page - 1) * PAGE_SIZE + 1}–${
                      (page - 1) * PAGE_SIZE + response.results.length
                    }`
                  : ""}
                {response.truncated
                  ? ` · only the first ${response.chunks_used} sections of a long resume were used`
                  : ""}
              </p>
              <label className="sort">
                Sort by
                <select aria-label="Sort by" defaultValue="best">
                  <option value="best">Best match</option>
                </select>
              </label>
            </div>

            {visible.length === 0 && (
              <p className="empty-note">
                No professor on this page mentions an open position. Clear that filter to see
                the other matches.
              </p>
            )}

            {visible.map((result) => (
              <MatchCard key={result.professor.id} result={result} terms={topics} />
            ))}

            {totalPages > 1 && (
              <nav className="pagination" aria-label="Match result pages">
                {pageWindow(page, totalPages).map((number) => (
                  <button
                    key={number}
                    type="button"
                    className={number === page ? "page-current" : undefined}
                    aria-current={number === page ? "page" : undefined}
                    disabled={loading}
                    onClick={() => runMatch(number)}
                  >
                    {number}
                  </button>
                ))}
                <button
                  type="button"
                  disabled={page >= totalPages || loading}
                  onClick={() => runMatch(page + 1)}
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

function MatchCard({ result, terms }: { result: MatchResult; terms: string[] }) {
  const { professor, matches } = result;
  const strong = relevanceLabel(result.similarity) === "Strong match";
  const saved = useIsSaved(professor.id);
  const quote = matches[0];

  return (
    <article className="prof-card">
      <div className="prof-top">
        <div className="avatar" aria-hidden="true">
          {initials(professor.name)}
        </div>
        <div className="prof-id">
          <h2>
            <Link href={`/professors/${professor.id}`}>{professor.name}</Link>
          </h2>
          <p>
            {professor.affiliation}
            {professor.country ? ` · ${professor.country}` : ""}
          </p>
        </div>
        <div className="match-badge">
          <span className={strong ? "match-pill strong" : "match-pill"}>
            {strong ? "Strong match" : "Good match"}
          </span>
        </div>
      </div>

      <p className="why-label">Why you match</p>
      {quote && (
        <div className="why-grid">
          <figure className="quote">
            <figcaption>
              <DocIcon />
              Your resume
            </figcaption>
            <blockquote>
              “{highlight(shorten(quote.resume_excerpt, 280), terms)}”
            </blockquote>
          </figure>
          <figure className="quote">
            <figcaption>
              <QuoteIcon />
              Their page
              {" · "}
              <a href={quote.url} target="_blank" rel="noreferrer">
                {quote.heading || quote.page_title || "Source page"}
              </a>
            </figcaption>
            <blockquote>“{highlight(shorten(quote.text, 280), terms)}”</blockquote>
          </figure>
        </div>
      )}

      <div className="card-actions">
        <Link className="btn-dark" href={`/professors/${professor.id}`}>
          View profile
        </Link>
        <a className="btn-ghost" href={professor.homepage} target="_blank" rel="noreferrer">
          Homepage
        </a>
        <button
          type="button"
          className="btn-icon"
          aria-pressed={saved}
          aria-label={saved ? `Remove ${professor.name} from saved` : `Save ${professor.name}`}
          onClick={() =>
            toggleSaved({
              id: professor.id,
              name: professor.name,
              affiliation: professor.affiliation,
              country: professor.country,
              homepage: professor.homepage,
            })
          }
        >
          <BookmarkIcon filled={saved} />
        </button>
      </div>
    </article>
  );
}

function useIsSaved(id: number): boolean {
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    const sync = () => setSaved(readSaved().some((item) => item.id === id));
    sync();
    window.addEventListener(SAVED_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(SAVED_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, [id]);
  return saved;
}

const TOPIC_HINTS = [
  "machine learning",
  "deep learning",
  "natural language processing",
  "computer vision",
  "human-computer interaction",
  "data science",
  "reinforcement learning",
  "computer security",
  "programming languages",
  "distributed systems",
  "computational biology",
  "bioinformatics",
  "healthcare",
  "robotics",
  "computer graphics",
  "operating systems",
  "cryptography",
  "artificial intelligence",
];

function topicsFromText(text: string): string[] {
  const found: string[] = [];
  const lowered = text.toLowerCase();
  for (const hint of TOPIC_HINTS) {
    if (lowered.includes(hint)) found.push(hint);
  }
  const lines = text.split(/\n/);
  for (const line of lines) {
    const skillish = /skill|interest|project|research|experience/i.test(line);
    const source = line.includes(":") ? line.split(":").slice(1).join(":") : skillish ? line : "";
    if (!source.trim()) continue;
    for (const part of source.split(/[,;•|]/)) {
      const clean = part
        .replace(/\(.*?\)/g, "")
        .replace(/\s+/g, " ")
        .trim();
      const words = clean.split(" ").filter(Boolean);
      if (words.length < 1 || words.length > 5) continue;
      if (clean.length < 3 || clean.length > 36) continue;
      if (/https?:|@|^\d/.test(clean)) continue;
      found.push(clean);
    }
  }
  const unique: string[] = [];
  for (const topic of found) {
    if (!unique.some((item) => item.toLowerCase() === topic.toLowerCase())) unique.push(topic);
  }
  return unique.slice(0, 4);
}

function highlight(text: string, terms: string[]) {
  const words = terms
    .flatMap((term) => term.split(/\s+/))
    .map((word) => word.replace(/[^\w'-]/g, ""))
    .filter((word) => word.length > 2);
  const unique = [...new Set(words.map((word) => word.toLowerCase()))];
  if (unique.length === 0) return text;
  const pattern = new RegExp(`(${unique.map(escapeRegExp).join("|")})`, "gi");
  return text.split(pattern).map((part, index) =>
    unique.includes(part.toLowerCase()) ? <mark key={index}>{part}</mark> : <span key={index}>{part}</span>,
  );
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function shorten(text: string, max: number): string {
  const flat = text.replace(/\s+/g, " ").trim();
  if (flat.length <= max) return flat;
  return flat.slice(0, max).replace(/\s+\S*$/, "") + "…";
}

function initials(name: string): string {
  const parts = name.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "•";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function fileKind(name: string): string {
  const ext = name.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return "PDF";
  if (ext === "docx") return "DOCX";
  if (ext === "md") return "MD";
  if (ext === "txt") return "TXT";
  return "FILE";
}

function pageWindow(current: number, total: number): number[] {
  const end = Math.min(total, Math.max(current + 2, 5));
  const start = Math.max(1, end - 4);
  const pages: number[] = [];
  for (let page = start; page <= Math.min(total, start + 4); page += 1) pages.push(page);
  return pages;
}

function DocIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
      <path
        d="M4 1.5h5.2L13 5.2V14a.5.5 0 0 1-.5.5h-8A.5.5 0 0 1 4 14V2a.5.5 0 0 1 .5-.5Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
      />
      <path d="M9 1.8V5h3.2" fill="none" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

function QuoteIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
      <path
        d="M3 10.2c0-2.4 1.3-4.4 3.2-5.4l.5 1c-1.1.6-1.7 1.6-1.8 2.6h1.8V13H3V10.2Zm6 0c0-2.4 1.3-4.4 3.2-5.4l.5 1c-1.1.6-1.7 1.6-1.8 2.6h1.8V13H9V10.2Z"
        fill="currentColor"
      />
    </svg>
  );
}

function BookmarkIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <path
        d="M4 2.5h8a.5.5 0 0 1 .5.5v11L8 11.2 3.5 14V3a.5.5 0 0 1 .5-.5Z"
        fill={filled ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
    </svg>
  );
}
