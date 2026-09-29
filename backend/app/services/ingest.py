"""Professor CSV ingestion: parse, validate, normalize, upsert."""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tables import Professor

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("name", "affiliation", "homepage")

# CSRankings uses this placeholder when the ORCID is unknown.
ORCID_PLACEHOLDER = "0000-0000-0000-0000"


@dataclass
class ProfessorRecord:
    name: str
    affiliation: str
    homepage: str
    scholar_id: str | None = None
    orcid: str | None = None
    country: str | None = None


class InvalidRecord(ValueError):
    pass


def normalize_url(url: str) -> str:
    """Normalize a homepage URL: add scheme, lowercase host, strip fragments
    and trailing slashes on bare paths."""
    url = url.strip()
    if not url:
        raise InvalidRecord("empty URL")
    if "://" not in url:
        url = "https://" + url
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise InvalidRecord(f"not an http(s) URL: {url!r}")
    path = parts.path or "/"
    normalized = urlunsplit((parts.scheme, parts.netloc.lower(), path, parts.query, ""))
    if normalized.endswith("/") and parts.query == "" and path == "/":
        pass  # keep the root slash
    return normalized


def parse_record(row: dict[str, str]) -> ProfessorRecord:
    """Validate and normalize one CSV row."""
    cleaned = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
    for field in REQUIRED_FIELDS:
        if not cleaned.get(field):
            raise InvalidRecord(f"missing required field {field!r} in row {row!r}")

    scholar_id = cleaned.get("scholarid") or cleaned.get("scholar_id") or None
    if scholar_id in ("", "NOSCHOLARPAGE"):
        scholar_id = None
    orcid = cleaned.get("orcid") or None
    if orcid == ORCID_PLACEHOLDER:
        orcid = None

    # DBLP disambiguates repeated names with a numeric suffix ("Wei Wang 0004")
    # that means nothing to users; drop it for display. Distinct same-named
    # people at one university would collide on (name, affiliation) — none do
    # in this data, and the DB constraint would surface it if one ever did.
    name = re.sub(r" \d{4}$", "", cleaned["name"])

    return ProfessorRecord(
        name=name,
        affiliation=cleaned["affiliation"],
        homepage=normalize_url(cleaned["homepage"]),
        scholar_id=scholar_id,
        orcid=orcid,
        country=cleaned.get("country") or None,
    )


def read_csv(path: str | Path) -> tuple[list[ProfessorRecord], list[str]]:
    """Read the professors CSV. Returns (valid records, error messages).

    Duplicate (name, affiliation) pairs within the file are collapsed,
    keeping the first occurrence.
    """
    records: list[ProfessorRecord] = []
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    seen_homepages: dict[tuple[str, str], str] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for line_no, row in enumerate(csv.DictReader(f), start=2):
            try:
                record = parse_record(row)
            except InvalidRecord as exc:
                errors.append(f"line {line_no}: {exc}")
                continue
            key = (record.name, record.affiliation)
            if key in seen:
                errors.append(f"line {line_no}: duplicate professor {key}")
                continue
            # CSRankings lists the same person under several DBLP name
            # variants ("Alex Aiken" / "Alexander Aiken"); the homepage is the
            # stable identity, so same affiliation + same homepage = alias.
            alias_key = (record.affiliation, record.homepage)
            if alias_key in seen_homepages:
                errors.append(
                    f"line {line_no}: {record.name!r} is an alias of "
                    f"{seen_homepages[alias_key]!r} (same homepage), skipped"
                )
                continue
            seen.add(key)
            seen_homepages[alias_key] = record.name
            records.append(record)
    return records, errors


def upsert_professors(session: Session, records: list[ProfessorRecord]) -> tuple[int, int]:
    """Insert new professors / update existing ones. Returns (inserted, updated).

    Uniqueness keys: (name, affiliation) — enforced by a DB constraint — and
    (affiliation, homepage), which catches the same person listed under a
    different DBLP name variant.
    """
    inserted = updated = 0
    for record in records:
        existing = session.execute(
            select(Professor).where(
                Professor.name == record.name,
                Professor.affiliation == record.affiliation,
            )
        ).scalar_one_or_none()
        if existing is None:
            # Same homepage at the same university => same person under an
            # alias; update that row instead of inserting a duplicate.
            existing = session.execute(
                select(Professor).where(
                    Professor.affiliation == record.affiliation,
                    Professor.homepage == record.homepage,
                )
            ).scalar_one_or_none()
        if existing is None:
            session.add(
                Professor(
                    name=record.name,
                    affiliation=record.affiliation,
                    homepage=record.homepage,
                    scholar_id=record.scholar_id,
                    orcid=record.orcid,
                    country=record.country,
                )
            )
            inserted += 1
        else:
            changed = False
            for field in ("homepage", "scholar_id", "orcid", "country"):
                new_value = getattr(record, field)
                if new_value and getattr(existing, field) != new_value:
                    setattr(existing, field, new_value)
                    changed = True
            if changed:
                updated += 1
    session.commit()
    return inserted, updated
