"""
Import book entries from a CSV file into the `_books/` collection.

Expected CSV columns (case-sensitive): title, authors, comments, isbn, id,
uuid, pubdate, rating, tags, languages. Extra columns are ignored.

Usage:
  python _scripts/import_books_from_csv.py _data/books.csv
"""

import csv
import datetime
import re
import sys
from pathlib import Path

DEFAULT_INPUT = Path("_data/books.csv")
BOOKS_DIR = Path("_books")


def safe_slug(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text or "book"


def parse_year(value: str) -> str:
    if not value:
        return ""
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return str(datetime.datetime.strptime(value[: len(fmt)], fmt).year)
        except Exception:
            continue
    return ""


def to_list(value: str) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[;, ]+", value)
    return [p for p in (part.strip() for part in parts) if p]


def quote(value: str) -> str:
    return f'"{value.replace("\"", r"\\\"")}"'


def render_list(items: list[str]) -> str:
    if not items:
        return "[]"
    escaped = [quote(item) for item in items]
    return f"[{', '.join(escaped)}]"


def clean_isbn(candidate: str) -> str:
    digits = re.sub(r"[^0-9Xx]", "", candidate)
    if len(digits) == 13:
        return digits
    if len(digits) == 10:
        return digits
    return ""


def extract_isbn_from_identifiers(value: str) -> str:
    if not value:
        return ""
    for part in value.split(","):
        key_value = part.split(":", 1)
        if len(key_value) != 2:
            continue
        key, val = key_value
        if key.lower().strip() == "isbn":
            cleaned = clean_isbn(val)
            if cleaned:
                return cleaned
    return ""


def find_isbn(row: dict) -> str:
    # 1) direct isbn column
    direct = clean_isbn((row.get("isbn") or "").replace("-", ""))
    if direct:
        return direct

    # 2) identifiers column like "mobi-asin:...,isbn:978..."
    ident = extract_isbn_from_identifiers(row.get("identifiers", ""))
    if ident:
        return ident

    # 3) scan free-form fields (comments) for isbn-like patterns
    for field in ("comments",):
        val = row.get(field) or ""
        matches = re.findall(r"(97[89][- ]?\\d{1,5}[- ]?\\d{1,7}[- ]?\\d{1,7}[- ]?[0-9Xx])", val)
        for m in matches:
            cleaned = clean_isbn(m)
            if cleaned:
                return cleaned

    return ""


def build_front_matter(row: dict) -> list[str]:
    title = row.get("title") or "Untitled"
    authors = row.get("authors") or row.get("author") or ""
    isbn = find_isbn(row)
    year = parse_year(row.get("pubdate", ""))
    stars = (row.get("rating") or "").strip()
    tags = to_list(row.get("tags", ""))
    languages = to_list(row.get("languages", ""))

    lines = [
        "---",
        "layout: book-review",
        f"title: {quote(title)}",
        f"author: {quote(authors)}" if authors else None,
        f"isbn: {isbn}" if isbn else None,
        f"released: {year}" if year else None,
        f"stars: {stars}" if stars else None,
        f"languages: {render_list(languages)}" if languages else None,
        f"tags: {render_list(tags)}" if tags else None,
        "status: Planned",
        "---",
    ]

    return [line for line in lines if line]


def make_slug(row: dict) -> str:
    if row.get("uuid"):
        return row["uuid"]
    if row.get("id"):
        return f"book-{row['id']}"
    return safe_slug(row.get("title", "book"))


def write_book(row: dict) -> Path:
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    slug = make_slug(row)
    path = BOOKS_DIR / f"{slug}.md"
    fm = build_front_matter(row)
    body = (row.get("comments") or "").strip()

    with path.open("w", encoding="utf-8") as f:
        f.write("\n".join(fm))
        f.write("\n\n")
        if body:
            f.write(body)
        f.write("\n")

    return path


def main() -> None:
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT
    if not input_path.exists():
        raise SystemExit(f"CSV not found: {input_path}")

    with input_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            path = write_book(row)
            count += 1
            print(f"Wrote {path}")

    print(f"Imported {count} books into {BOOKS_DIR}/")


if __name__ == "__main__":
    main()
