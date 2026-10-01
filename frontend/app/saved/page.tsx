"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { readSaved, SAVED_EVENT, toggleSaved, type SavedProfessor } from "@/lib/saved";

export default function SavedPage() {
  const [items, setItems] = useState<SavedProfessor[]>([]);

  useEffect(() => {
    const sync = () => setItems(readSaved());
    sync();
    window.addEventListener(SAVED_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(SAVED_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  return (
    <main>
      <Link className="back-link" href="/">
        ← Back to search
      </Link>
      <section className="hero">
        <h1>Saved professors</h1>
        <p>Professors you bookmark stay in this browser. Nothing is sent to a server.</p>
      </section>

      {items.length === 0 ? (
        <p className="empty-note">
          No one saved yet. Search for a topic, then bookmark a professor to keep them here.
        </p>
      ) : (
        <ul className="saved-list">
          {items.map((professor) => (
            <li key={professor.id} className="prof-card saved-row">
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
              <div className="card-actions">
                <Link className="btn-dark" href={`/professors/${professor.id}`}>
                  View profile
                </Link>
                <a className="btn-ghost" href={professor.homepage} target="_blank" rel="noreferrer">
                  Homepage
                </a>
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => toggleSaved(professor)}
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

function initials(name: string): string {
  const parts = name.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "•";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
