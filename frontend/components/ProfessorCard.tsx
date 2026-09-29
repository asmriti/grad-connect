import Link from "next/link";
import { relevanceLabel, type SearchResult } from "@/lib/api";

export default function ProfessorCard({ result }: { result: SearchResult }) {
  const { professor, evidence } = result;
  return (
    <article className="result-card">
      <div className="result-head">
        <h2>
          <Link href={`/professors/${professor.id}`}>{professor.name}</Link>
        </h2>
        <span className="relevance">{relevanceLabel(result.similarity)}</span>
      </div>
      <p className="result-meta">
        {professor.affiliation}
        {professor.country ? ` · ${professor.country}` : ""}
      </p>

      {evidence.map((item, i) => (
        <figure className="evidence" key={i}>
          <blockquote>“{truncate(item.text, 320)}”</blockquote>
          <cite>
            {item.heading ? `${item.heading} — ` : ""}
            <a href={item.url} target="_blank" rel="noreferrer">
              {item.page_title || item.url}
            </a>
          </cite>
        </figure>
      ))}

      <div className="result-actions">
        <Link href={`/professors/${professor.id}`}>View professor</Link>
        <a href={professor.homepage} target="_blank" rel="noreferrer">
          Homepage ↗
        </a>
      </div>
    </article>
  );
}

function truncate(text: string, max: number): string {
  const flat = text.replace(/\s+/g, " ").trim();
  if (flat.length <= max) return flat;
  return flat.slice(0, max).replace(/\s+\S*$/, "") + "…";
}
