"""
Import book entries from a CSV file into the `_books/` collection.

Expected CSV columns (case-sensitive): title, authors, comments, isbn, id,
uuid, pubdate, rating, tags, languages. Extra columns are ignored.

Usage:
  python _scripts/import_books_from_csv.py _data/books.csv
"""

import csv
import datetime
import os
import re
import sys
import shutil
import json
from pathlib import Path
from urllib import request, error

ALLOWED_CATEGORIES = {
    "Engineering",
    "Science",
    "Fiction",
    "Nonfiction",
    "Business",
    "Psychology",
    "Arts",
    "Physical Health",
    "Uncategorized",
}

# Optional AI classification (set OPENAI_API_KEY to enable).
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
AI_MODEL = os.getenv("AI_CLASSIFIER_MODEL", "gpt-4o-mini").strip()
AI_TIMEOUT = float(os.getenv("AI_CLASSIFIER_TIMEOUT", "8").strip() or 8)

# Base tag-to-category hints (aligns with category_map in _pages/books.md).
TAG_CATEGORY_HINTS = {
    # Existing mappings
    "comp_programming": "Engineering",
    "programming": "Engineering",
    "engineering": "Engineering",
    "security": "Engineering",
    "cloud": "Engineering",
    "devops": "Engineering",
    "infrastructure": "Engineering",
    "web": "Engineering",
    "software": "Engineering",
    "sci_psychology": "Science",
    "literature_19": "Fiction",
    "prose_rus_classic": "Fiction",
    "child_prose": "Fiction",
    "nonfiction": "Nonfiction",
    # New high-level shortcuts
    "business": "Business",
    "psychology": "Psychology",
    "arts": "Arts",
    "physical_health": "Physical Health",
    "health": "Physical Health",
    "fitness": "Physical Health",
    "running": "Physical Health",
}

# Keyword hints searched in title/comments for each category (best-effort).
KEYWORD_HINTS = {
    "Engineering": [
        "programming",
        "software",
        "engineering",
        "systems",
        "system",
        "algorithm",
        "computer",
        "developer",
        "devops",
        "code",
        "ai",
        "machine learning",
        "ml",
        "data science",
        "cloud",
        "aws",
        "azure",
        "gcp",
        "kubernetes",
        "docker",
        "containers",
        "security",
        "secure",
        "infosec",
        "cybersecurity",
        "network security",
        "application security",
        "web security",
        "web application security",
        "sre",
        "site reliability",
        "observability",
        "monitoring",
        "logging",
        "infrastructure",
        "iac",
        "terraform",
        "ansible",
        "policy as code",
    ],
    "Science": [
        "science",
        "physics",
        "chemistry",
        "biology",
        "math",
        "mathematics",
        "discrete math",
        "discrete mathematics",
        "astronomy",
        "geology",
        "cognitive",
        "neuroscience",
    ],
    "Psychology": [
        "psychology",
        "psychological",
        "cognitive",
        "mind",
        "behavior",
        "behaviour",
        "brain",
    ],
    "Business": [
        "business",
        "startup",
        "start-up",
        "strategy",
        "management",
        "leadership",
        "marketing",
        "sales",
        "finance",
        "economics",
        "entrepreneur",
    ],
    "Arts": [
        "art",
        "arts",
        "design",
        "music",
        "painting",
        "photography",
        "film",
        "cinema",
        "theater",
        "theatre",
        "language",
    ],
    "Physical Health": [
        "health",
        "fitness",
        "exercise",
        "training",
        "run",
        "running",
        "marathon",
        "triathlon",
        "sport",
        "sports",
        "athlete",
        "coaching",
        "diet",
        "dieting",
        "nutrition",
        "wellness",
    ],
    "Fiction": [
        "novel",
        "story",
        "stories",
        "fiction",
        "fantasy",
        "sci-fi",
        "science fiction",
        "thriller",
        "romance",
        "mystery",
        "prose",
        "classic",
    ],
    "Nonfiction": [
        "nonfiction",
        "non-fiction",
        "biography",
        "memoir",
        "history",
        "essay",
        "reportage",
    ],
}

DEFAULT_INPUT = Path("_data/books.csv")
BOOKS_DIR = Path("_books")
BOOK_COVERS_DIR = Path("assets/img/book_covers")
BOOK_COVERS_URL_PREFIX = "assets/img/book_covers"


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


def extract_asin_from_identifiers(value: str) -> str:
    if not value:
        return ""
    for part in value.split(","):
        key_value = part.split(":", 1)
        if len(key_value) != 2:
            continue
        key, val = key_value
        key = key.lower().strip()
        if "asin" in key:
            cleaned = re.sub(r"[^A-Za-z0-9]", "", val)
            if cleaned:
                return cleaned
    return ""


def find_cover(row: dict, isbn: str) -> str:
    # If cover provided, respect it.
    cover = (row.get("cover") or "").strip()
    if cover:
        local_cover = maybe_copy_cover(cover, row)
        if local_cover:
            return local_cover
        return cover

    # Prefer Open Library cover by ISBN.
    if isbn:
        return f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"

    # Fallback to ASIN if present in identifiers.
    asin = extract_asin_from_identifiers(row.get("identifiers", ""))
    if asin:
        return f"https://covers.openlibrary.org/b/asin/{asin}-L.jpg"

    return ""

def maybe_copy_cover(path_str: str, row: dict) -> str:
    """Copy a local cover image into the site's cover directory and return its relative URL."""
    src = Path(path_str).expanduser()
    if not src.exists() or not src.is_file():
        return ""

    BOOK_COVERS_DIR.mkdir(parents=True, exist_ok=True)

    slug = make_slug(row)
    ext = src.suffix if src.suffix else ".jpg"
    dest = BOOK_COVERS_DIR / f"{slug}{ext}"
    try:
        shutil.copyfile(src, dest)
    except Exception:
        return ""

    return f"{BOOK_COVERS_URL_PREFIX}/{dest.name}"


def build_front_matter(row: dict) -> list[str]:
    title = row.get("title") or "Untitled"
    authors = row.get("authors") or row.get("author") or ""
    isbn = find_isbn(row)
    cover = find_cover(row, isbn)
    year = parse_year(row.get("pubdate", ""))
    stars = (row.get("rating") or "").strip()
    tags = to_list(row.get("tags", ""))
    languages = to_list(row.get("languages", ""))
    category = detect_category(title, tags, row.get("comments", ""))

    lines = [
        "---",
        "layout: book-review",
        f"title: {quote(title)}",
        f"author: {quote(authors)}" if authors else None,
        f"isbn: {isbn}" if isbn else None,
        f"cover: {cover}" if cover else None,
        f"released: {year}" if year else None,
        f"stars: {stars}" if stars else None,
        f"languages: {render_list(languages)}" if languages else None,
        f"tags: {render_list(tags)}" if tags else None,
        f"categories: {render_list([category])}" if category else None,
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


def normalize(text: str) -> str:
    return (text or "").lower()


def detect_category(title: str, tags: list[str], comments: str) -> str:
    # 0) Try AI if configured
    ai_guess = detect_category_ai(title, tags, comments)
    if ai_guess:
        return ai_guess

    # 1) Tag-based mapping
    for tag in tags:
        mapped = TAG_CATEGORY_HINTS.get(tag.lower())
        if mapped in ALLOWED_CATEGORIES:
            return mapped

    # 2) Keyword scan in tags, title, comments
    text_blob = " ".join(tags + [title, comments or ""]).lower()
    for category, hints in KEYWORD_HINTS.items():
        for hint in hints:
            if hint in text_blob:
                return category if category in ALLOWED_CATEGORIES else "Uncategorized"

    # 3) Fallback
    return "Uncategorized"


def detect_category_ai(title: str, tags: list[str], comments: str) -> str | None:
    if not OPENAI_API_KEY:
        return None

    allowed_list = sorted(ALLOWED_CATEGORIES)
    prompt = (
        "You classify books into exactly one of these categories. "
        "Return only the category name. If unsure, return 'Uncategorized'. "
        "Definitions: "
        "Engineering = programming, software, security, cloud, devops, systems, infra, web, SRE. "
        "Science = math, physics, discrete math, biology, neuroscience, research. "
        "Business = business, startups, management, finance, strategy. "
        "Psychology = psychology, cognition, behavior, brain. "
        "Arts = design, art, music, film, theater. "
        "Physical Health = fitness, sports, running, training, diet, nutrition, wellness. "
        "Fiction = novels, stories, literature. "
        "Nonfiction = biography, memoir, history, essays, reportage. "
        "Favor Engineering for systems, security, cloud, programming; do not place those in Nonfiction. "
        f"Allowed: {', '.join(allowed_list)}. "
        f"Title: {title or 'N/A'}. "
        f"Tags: {', '.join(tags) if tags else 'None'}. "
        f"Description: {comments or 'None'}."
    )

    body = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": "You classify books into high-level categories."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 10,
    }

    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=AI_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
            guess = (content or "").strip()
            # Some models might return extra text; take first token by delimiter/newline.
            guess = re.split(r"[\n,;]", guess)[0].strip()
            if guess in ALLOWED_CATEGORIES:
                return guess
    except Exception:
        return None

    return None


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
