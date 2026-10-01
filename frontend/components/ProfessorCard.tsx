"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { relevanceLabel, type SearchResult } from "@/lib/api";
import { readSaved, SAVED_EVENT, toggleSaved, type SavedProfessor } from "@/lib/saved";

export default function ProfessorCard({
  result,
  terms,
}: {
  result: SearchResult;
  terms: string[];
}) {
  const { professor, evidence } = result;
  const label = relevanceLabel(result.similarity);
  const strong = label === "Strong match";
  const blob = evidence.map((item) => item.text).join(" ");
  const tags = recruitingTags(blob);
  const caution = cautionSentence(blob);
  const saved = useIsSaved(professor.id);

  function onSave() {
    toggleSaved({
      id: professor.id,
      name: professor.name,
      affiliation: professor.affiliation,
      country: professor.country,
      homepage: professor.homepage,
    });
  }

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
          {tags.length > 0 && (
            <ul className="tag-row">
              {tags.map((tag) => (
                <li key={tag}>{tag}</li>
              ))}
            </ul>
          )}
        </div>
        <div className="match-badge">
          <span className={strong ? "match-pill strong" : "match-pill"}>
            {strong ? "Strong match" : "Good match"}
          </span>
          <span className="passage-count">
            {evidence.length} cited {evidence.length === 1 ? "passage" : "passages"}
          </span>
        </div>
      </div>

      {evidence.map((item, i) => {
        const onHomepage =
          item.url.replace(/\/$/, "") === professor.homepage.replace(/\/$/, "");
        return (
          <figure className="quote" key={i}>
            <blockquote>
              <span aria-hidden="true">“</span>
              {highlight(truncate(item.text, 420), terms)}
              <span aria-hidden="true">”</span>
            </blockquote>
            <figcaption>
              <a href={item.url} target="_blank" rel="noreferrer">
                {item.heading || item.page_title || "Source page"}
              </a>
              <span>
                {" "}
                · {professor.name}&apos;s {onHomepage ? "homepage" : "page"}
              </span>
            </figcaption>
          </figure>
        );
      })}

      {caution && (
        <p className="heads-up">
          <span aria-hidden="true">Heads up: </span>
          {truncate(caution, 220)}
        </p>
      )}

      <div className="card-actions">
        <Link className="btn-dark" href={`/professors/${professor.id}`}>
          View profile
        </Link>
        <a className="btn-ghost" href={professor.homepage} target="_blank" rel="noreferrer">
          Homepage
          <ExternalIcon />
        </a>
        <button
          type="button"
          className="btn-icon"
          aria-pressed={saved}
          aria-label={saved ? `Remove ${professor.name} from saved` : `Save ${professor.name}`}
          onClick={onSave}
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

function initials(name: string): string {
  const parts = name
    .replace(/[^A-Za-z\s'-]/g, "")
    .split(/\s+/)
    .filter((part) => part && part !== "-");
  if (parts.length === 0) return "•";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function truncate(text: string, max: number): string {
  const flat = text.replace(/\s+/g, " ").trim();
  if (flat.length <= max) return flat;
  return flat.slice(0, max).replace(/\s+\S*$/, "") + "…";
}

function highlight(text: string, terms: string[]) {
  const words = terms
    .flatMap((term) => term.split(/\s+/))
    .map((word) => word.replace(/[^\w']/g, ""))
    .filter((word) => word.length > 2);
  const unique = [...new Set(words.map((word) => word.toLowerCase()))];
  if (unique.length === 0) return text;
  const pattern = new RegExp(`(${unique.map(escapeRegExp).join("|")})`, "gi");
  const parts = text.split(pattern);
  return parts.map((part, i) =>
    unique.includes(part.toLowerCase()) ? <mark key={i}>{part}</mark> : <span key={i}>{part}</span>,
  );
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const SEEKING = /looking for|recruiting|accepting|seeking|join the group|welcome|interested in/i;

function recruitingTags(text: string): string[] {
  if (!SEEKING.test(text)) return [];
  const tags: string[] = [];
  if (/ph\.?\s?d/i.test(text)) tags.push("Recruiting PhD");
  if (/master'?s/i.test(text)) tags.push("Recruiting master's");
  if (/undergrad/i.test(text)) tags.push("Recruiting undergrads");
  return tags;
}

const CAUTION =
  /not currently accepting|not accepting|only advising|only currently advising|no longer accepting|not recruiting|do not have openings/i;

function cautionSentence(text: string): string | null {
  const sentences = text.split(/(?<=[.!?])\s+/);
  return sentences.find((sentence) => CAUTION.test(sentence)) ?? null;
}

function ExternalIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
      <path
        d="M4 2.5H2.5v7h7V8M6.5 2.5H9.5V5.5M9.2 2.8 5.2 6.8"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
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

