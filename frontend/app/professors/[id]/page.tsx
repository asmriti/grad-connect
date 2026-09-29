"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import { fetchProfessor, type ProfessorDetail } from "@/lib/api";

/** Goes back in history (preserving the search on the homepage) when the
 * visitor came from within the app; falls back to a plain link to "/" when
 * this page was opened directly. */
function BackToSearch() {
  const router = useRouter();
  const [canGoBack, setCanGoBack] = useState(false);

  useEffect(() => {
    setCanGoBack(window.history.length > 1);
  }, []);

  if (!canGoBack) {
    return (
      <Link className="back-link" href="/">
        ← Back to search
      </Link>
    );
  }
  return (
    <a
      className="back-link"
      href="/"
      onClick={(e) => {
        e.preventDefault();
        router.back();
      }}
    >
      ← Back to search
    </a>
  );
}

export default function ProfessorPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [detail, setDetail] = useState<ProfessorDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchProfessor(id)
      .then(setDetail)
      .catch(() => setError("This professor could not be loaded."));
  }, [id]);

  if (error) {
    return (
      <main>
        <p className="error-note">{error}</p>
        <Link className="back-link" href="/">
          ← Back to search
        </Link>
      </main>
    );
  }

  if (!detail) {
    return (
      <main>
        <p className="empty-note">Loading…</p>
      </main>
    );
  }

  const { professor, documents, chunks } = detail;

  return (
    <main>
      <BackToSearch />

      <header className="detail-header">
        <h1>{professor.name}</h1>
        <p className="result-meta">
          {professor.affiliation}
          {professor.country ? ` · ${professor.country}` : ""}
        </p>
        <div className="detail-links">
          <a href={professor.homepage} target="_blank" rel="noreferrer">
            Homepage ↗
          </a>
          {professor.scholar_id && (
            <a
              href={`https://scholar.google.com/citations?user=${professor.scholar_id}`}
              target="_blank"
              rel="noreferrer"
            >
              Google Scholar ↗
            </a>
          )}
          {professor.orcid && (
            <a
              href={`https://orcid.org/${professor.orcid}`}
              target="_blank"
              rel="noreferrer"
            >
              ORCID ↗
            </a>
          )}
        </div>
      </header>

      <h2 className="section-title">Indexed pages</h2>
      {documents.length === 0 ? (
        <p className="empty-note">
          No pages indexed yet. Run the indexing pipeline to crawl this
          professor&apos;s site.
        </p>
      ) : (
        <ul className="page-list">
          {documents.map((doc) => (
            <li key={doc.id}>
              <a href={doc.url} target="_blank" rel="noreferrer">
                {doc.title || doc.url}
              </a>
            </li>
          ))}
        </ul>
      )}

      <h2 className="section-title">Research evidence</h2>
      {chunks.length === 0 ? (
        <p className="empty-note">
          No text has been extracted from this professor&apos;s pages yet.
        </p>
      ) : (
        chunks.map((chunk) => (
          <figure className="evidence" key={chunk.id} style={{ marginBottom: "1rem" }}>
            <blockquote>{chunk.text}</blockquote>
            <cite>
              {chunk.heading ? `${chunk.heading} — ` : ""}
              <a href={chunk.url} target="_blank" rel="noreferrer">
                {chunk.page_title || chunk.url}
              </a>
            </cite>
          </figure>
        ))
      )}
    </main>
  );
}
