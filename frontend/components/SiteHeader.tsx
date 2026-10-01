"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function SiteHeader() {
  const path = usePathname();
  const searchActive = path === "/" || path.startsWith("/professors");
  const matchActive = path.startsWith("/match");
  const savedActive = path.startsWith("/saved");

  return (
    <header className="topbar">
      <Link className="brand" href="/">
        Grad Connect
      </Link>
      <nav className="nav-pills" aria-label="Main">
        <Link href="/" aria-current={searchActive ? "page" : undefined}>
          Search
        </Link>
        <Link href="/match" aria-current={matchActive ? "page" : undefined}>
          Match my resume
        </Link>
        <Link href="/saved" aria-current={savedActive ? "page" : undefined}>
          <BookmarkIcon />
          Saved
        </Link>
      </nav>
    </header>
  );
}

function BookmarkIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
      <path
        d="M4 2.5h8a.5.5 0 0 1 .5.5v11L8 11.2 3.5 14V3a.5.5 0 0 1 .5-.5Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
    </svg>
  );
}
