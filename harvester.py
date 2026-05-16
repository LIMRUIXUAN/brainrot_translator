"""Daily ETL harvester for slang and brainrot data.

The harvester extracts slang-like text from public sources, cleans and chunks it,
embeds each item, and writes vectors to Pinecone plus metadata to PostgreSQL.
It is intentionally a CLI writer only; the inference API reads from the stores.
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import logging
import os
import re
import socket
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterable, Literal

import requests
from dateutil.parser import isoparse
from dotenv import load_dotenv
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


LOGGER = logging.getLogger("harvester")
MODEL_NAME = "all-MiniLM-L6-v2"
SEED_TERMS = [
    "rizz",
    "no cap",
    "slay",
    "based",
    "bussin",
    "goated",
    "delulu",
    "it's giving",
    "era",
    "sigma",
    "ratio",
    "W",
    "L",
    "mid",
    "NPC",
    "vibe check",
    "brain rot",
    "fr fr",
    "lowkey",
    "highkey",
    "sus",
    "main character",
    "beige flag",
]
REDDIT_SUBREDDITS = [
    "GenZ",
    "TikTokCringe",
    "teenagers",
    "memes",
    "dankmemes",
    "Showerthoughts",
    "rant",
    "unpopularopinion",
]
TWITCH_CHANNELS = ["#xqc", "#hasanabi", "#pokimane", "#ludwig", "#nmplol"]

model: Any | None = None
db_pool: Any | None = None


@dataclass(frozen=True)
class Config:
    """Runtime settings loaded from environment variables."""

    reddit_client_id: str
    reddit_client_secret: str
    reddit_user_agent: str
    pinecone_api_key: str
    pinecone_index_name: str
    pinecone_environment: str
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    reddit_post_limit: int
    urban_dict_term_limit: int
    comment_depth: int
    min_upvote_ratio: float
    min_reddit_score: int
    batch_size: int
    request_delay_seconds: float
    twitch_oauth_token: str
    twitch_bot_username: str


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing."""


class RateLimitedError(RuntimeError):
    """Raised when a source returns a retryable rate-limit response."""


def setup_logging() -> None:
    """Configure console and rotating file logging."""

    log_format = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    file_handler = RotatingFileHandler(
        log_dir / "harvester.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    stream_handler = logging.StreamHandler()

    formatter = logging.Formatter(log_format)
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)


def env_int(name: str, default: int) -> int:
    """Read an integer from the environment with a default."""

    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc


def env_float(name: str, default: float) -> float:
    """Read a float from the environment with a default."""

    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a float") from exc


def load_config() -> Config:
    """Load all runtime configuration from environment variables."""

    return Config(
        reddit_client_id=os.getenv("REDDIT_CLIENT_ID", ""),
        reddit_client_secret=os.getenv("REDDIT_CLIENT_SECRET", ""),
        reddit_user_agent=os.getenv("REDDIT_USER_AGENT", ""),
        pinecone_api_key=os.getenv("PINECONE_API_KEY", ""),
        pinecone_index_name=os.getenv("PINECONE_INDEX_NAME", ""),
        pinecone_environment=os.getenv("PINECONE_ENVIRONMENT", ""),
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=env_int("POSTGRES_PORT", 5432),
        postgres_db=os.getenv("POSTGRES_DB", ""),
        postgres_user=os.getenv("POSTGRES_USER", ""),
        postgres_password=os.getenv("POSTGRES_PASSWORD", ""),
        reddit_post_limit=env_int("REDDIT_POST_LIMIT", 50),
        urban_dict_term_limit=env_int("URBAN_DICT_TERM_LIMIT", 100),
        comment_depth=env_int("COMMENT_DEPTH", 3),
        min_upvote_ratio=env_float("MIN_UPVOTE_RATIO", 0.6),
        min_reddit_score=env_int("MIN_REDDIT_SCORE", 10),
        batch_size=env_int("BATCH_SIZE", 64),
        request_delay_seconds=env_float("REQUEST_DELAY_SECONDS", 1.5),
        twitch_oauth_token=os.getenv("TWITCH_OAUTH_TOKEN", ""),
        twitch_bot_username=os.getenv("TWITCH_BOT_USERNAME", ""),
    )


def validate_env(
    config: Config,
    selected_source: Literal["urban", "reddit", "twitch"] | None,
    dry_run: bool,
) -> None:
    """Validate required environment variables for the requested execution."""

    sources = {selected_source} if selected_source else {"urban", "reddit", "twitch"}
    missing: list[str] = []

    if "reddit" in sources:
        reddit_required = {
            "REDDIT_CLIENT_ID": config.reddit_client_id,
            "REDDIT_CLIENT_SECRET": config.reddit_client_secret,
            "REDDIT_USER_AGENT": config.reddit_user_agent,
        }
        missing.extend(name for name, value in reddit_required.items() if not value)

    if not dry_run:
        load_required = {
            "PINECONE_API_KEY": config.pinecone_api_key,
            "PINECONE_INDEX_NAME": config.pinecone_index_name,
            "PINECONE_ENVIRONMENT": config.pinecone_environment,
            "POSTGRES_DB": config.postgres_db,
            "POSTGRES_USER": config.postgres_user,
            "POSTGRES_PASSWORD": config.postgres_password,
        }
        missing.extend(name for name, value in load_required.items() if not value)

    if missing:
        names = ", ".join(sorted(set(missing)))
        raise ConfigurationError(f"Missing required environment variables: {names}")

    if "twitch" in sources and config.twitch_oauth_token and not config.twitch_oauth_token.startswith("oauth:"):
        LOGGER.warning("TWITCH_OAUTH_TOKEN should usually start with 'oauth:'")


def print_setup_instructions() -> None:
    """Print first-run setup instructions for local operators."""

    if Path(".env").exists() and Path(".env").stat().st_size > 0:
        return
    print(
        "First run setup: copy .env.example to .env, fill required credentials, "
        "run db/schema.sql against PostgreSQL, then run python harvester.py."
    )


def setup_database(config: Config, dry_run: bool) -> None:
    """Create the PostgreSQL pool and apply db/schema.sql unless this is a dry run."""

    global db_pool
    if dry_run:
        LOGGER.info("Dry run enabled; skipping PostgreSQL setup")
        return

    try:
        from psycopg2.pool import ThreadedConnectionPool
    except ImportError as exc:
        raise ConfigurationError("PostgreSQL loading requires psycopg2-binary. Run: pip install -r requirements.txt") from exc

    db_pool = ThreadedConnectionPool(
        minconn=1,
        maxconn=5,
        host=config.postgres_host,
        port=config.postgres_port,
        dbname=config.postgres_db,
        user=config.postgres_user,
        password=config.postgres_password,
    )

    conn = db_pool.getconn()
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(Path("db/schema.sql").read_text(encoding="utf-8"))
        LOGGER.info("PostgreSQL schema is ready")
    finally:
        db_pool.putconn(conn)


def close_database_pool() -> None:
    """Close the PostgreSQL pool at process exit."""

    global db_pool
    if db_pool is not None:
        db_pool.closeall()
        db_pool = None


atexit.register(close_database_pool)


def clean_text(text: str, remove_brackets: bool = False) -> str:
    """Remove low-signal markup, URLs, emojis, and excess whitespace."""

    if remove_brackets:
        text = re.sub(r"\[([^\]]+)\]", r"\1", text)
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def text_hash(text: str) -> str:
    """Return a stable SHA-256 hash for raw text."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@retry(
    retry=retry_if_exception_type((requests.RequestException, RateLimitedError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=30),
    reraise=True,
)
def fetch_urban_definition(term: str) -> dict[str, Any] | None:
    """Fetch one Urban Dictionary definition payload with retry handling."""

    response = requests.get(
        "https://api.urbandictionary.com/v0/define",
        params={"term": term},
        timeout=10,
    )
    if response.status_code == 429:
        LOGGER.warning("Urban Dictionary rate limited; sleeping 60s")
        time.sleep(60)
        raise RateLimitedError("Urban Dictionary returned HTTP 429")
    if response.status_code >= 500:
        LOGGER.warning("Urban Dictionary HTTP %s for term %s", response.status_code, term)
        return None
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        LOGGER.warning("Urban Dictionary returned bad JSON for term %s", term)
        return None


def extract_urban_dictionary(terms: list[str], config: Config) -> list[dict[str, Any]]:
    """Extract and filter definitions from Urban Dictionary."""

    LOGGER.info("Urban Dictionary extraction started for %s terms", len(terms))
    items: list[dict[str, Any]] = []
    for term in terms[: config.urban_dict_term_limit]:
        try:
            payload = fetch_urban_definition(term)
        except Exception as exc:
            LOGGER.exception("Urban Dictionary failed for %s: %s", term, exc)
            continue

        if not payload:
            continue

        for definition in payload.get("list", []):
            raw_definition = definition.get("definition", "")
            cleaned_definition = clean_text(raw_definition, remove_brackets=True)
            thumbs_up = int(definition.get("thumbs_up") or 0)
            thumbs_down = int(definition.get("thumbs_down") or 0)
            upvote_ratio = thumbs_up / (thumbs_up + thumbs_down + 1)
            if upvote_ratio < config.min_upvote_ratio:
                LOGGER.debug("Skipping %s due to low upvote ratio", term)
                continue
            if len(cleaned_definition) <= 20:
                LOGGER.debug("Skipping %s due to short definition", term)
                continue

            example = clean_text(definition.get("example", ""), remove_brackets=True)
            word = clean_text(definition.get("word") or term, remove_brackets=True)
            raw_text = clean_text(f"{word}. {cleaned_definition} {example}")
            items.append(
                {
                    "term": word,
                    "source": "urban_dict",
                    "definition": cleaned_definition,
                    "example": example,
                    "raw_text": raw_text,
                    "upvotes": thumbs_up,
                    "downvotes": thumbs_down,
                    "scraped_at": datetime.now(timezone.utc),
                }
            )

        time.sleep(config.request_delay_seconds)

    LOGGER.info("Urban Dictionary extraction finished with %s items", len(items))
    return items


def extract_reddit(config: Config) -> list[dict[str, Any]]:
    """Extract post/comment text from configured Reddit subreddits."""

    try:
        import praw
        from prawcore.exceptions import PrawcoreException, ResponseException
    except ImportError:
        LOGGER.error("Reddit extraction requires praw. Install dependencies with: pip install -r requirements.txt")
        return []

    LOGGER.info("Reddit extraction started")
    items: list[dict[str, Any]] = []
    try:
        reddit = praw.Reddit(
            client_id=config.reddit_client_id,
            client_secret=config.reddit_client_secret,
            user_agent=config.reddit_user_agent,
            read_only=True,
            requestor_kwargs={"timeout": 10},
        )
        for subreddit_name in REDDIT_SUBREDDITS:
            try:
                subreddit = reddit.subreddit(subreddit_name)
                for post in subreddit.hot(limit=config.reddit_post_limit):
                    post.comments.replace_more(limit=0)
                    for comment in post.comments:
                        if getattr(comment, "score", 0) < config.min_reddit_score:
                            continue
                        body = getattr(comment, "body", "")
                        if body in {"[deleted]", "[removed]"}:
                            continue
                        raw_text = clean_text(f"{post.title} {body}")
                        if len(raw_text) < 30:
                            LOGGER.debug("Skipping short Reddit text from r/%s", subreddit_name)
                            continue
                        items.append(
                            {
                                "term": "",
                                "source": "reddit",
                                "definition": None,
                                "example": None,
                                "raw_text": raw_text,
                                "upvotes": int(getattr(comment, "score", 0)),
                                "downvotes": 0,
                                "subreddit": subreddit_name,
                                "author": str(getattr(comment, "author", "") or ""),
                                "scraped_at": datetime.now(timezone.utc),
                            }
                        )
                LOGGER.info("Reddit r/%s complete; total items=%s", subreddit_name, len(items))
            except ResponseException as exc:
                if getattr(exc.response, "status_code", None) == 429:
                    LOGGER.warning("Reddit rate limited; sleeping 120s")
                    time.sleep(120)
                else:
                    LOGGER.exception("Reddit response error for r/%s", subreddit_name)
            except PrawcoreException:
                LOGGER.exception("Reddit PRAW error for r/%s", subreddit_name)
            time.sleep(1)
    except Exception:
        LOGGER.exception("Reddit extraction failed")

    LOGGER.info("Reddit extraction finished with %s items", len(items))
    return items


def is_single_all_caps_emote(text: str) -> bool:
    """Return whether text looks like a single all-caps Twitch emote token."""

    return bool(re.fullmatch(r"[A-Z0-9_]{2,}", text.strip()))


def extract_twitch(config: Config) -> list[dict[str, Any]]:
    """Extract live chat messages from Twitch IRC if credentials are configured."""

    if not config.twitch_oauth_token or not config.twitch_bot_username:
        LOGGER.info("Twitch credentials not configured; skipping Twitch extraction")
        return []

    LOGGER.info("Twitch extraction started")
    items: list[dict[str, Any]] = []
    for channel in TWITCH_CHANNELS:
        channel_count = 0
        try:
            with socket.create_connection(("irc.chat.twitch.tv", 6667), timeout=10) as sock:
                sock.settimeout(10)
                sock.sendall(f"PASS {config.twitch_oauth_token}\r\n".encode("utf-8"))
                sock.sendall(f"NICK {config.twitch_bot_username}\r\n".encode("utf-8"))
                sock.sendall(f"JOIN {channel}\r\n".encode("utf-8"))

                start = time.monotonic()
                while time.monotonic() - start < 90 and channel_count < 200:
                    try:
                        data = sock.recv(4096).decode("utf-8", errors="ignore")
                    except socket.timeout:
                        continue
                    if data.startswith("PING"):
                        sock.sendall("PONG :tmi.twitch.tv\r\n".encode("utf-8"))
                        continue
                    for line in data.splitlines():
                        match = re.search(r"PRIVMSG #[^ ]+ :(.+)$", line)
                        if not match:
                            continue
                        raw_text = clean_text(match.group(1))
                        if len(raw_text) < 15 or is_single_all_caps_emote(raw_text):
                            continue
                        items.append(
                            {
                                "term": "",
                                "source": "twitch",
                                "definition": None,
                                "example": None,
                                "raw_text": raw_text,
                                "upvotes": 0,
                                "downvotes": 0,
                                "channel": channel.lstrip("#"),
                                "scraped_at": datetime.now(timezone.utc),
                            }
                        )
                        channel_count += 1
                        if channel_count >= 200:
                            break
                LOGGER.info("Twitch %s complete with %s messages", channel, channel_count)
        except OSError:
            LOGGER.exception("Twitch extraction failed for %s", channel)

    LOGGER.info("Twitch extraction finished with %s items", len(items))
    return items


def extract_all(
    config: Config,
    selected_source: Literal["urban", "reddit", "twitch"] | None,
    terms: list[str],
) -> list[dict[str, Any]]:
    """Extract raw data from all requested sources."""

    items: list[dict[str, Any]] = []
    sources = {selected_source} if selected_source else {"urban", "reddit", "twitch"}
    if "urban" in sources:
        items.extend(extract_urban_dictionary(terms, config))
    if "reddit" in sources:
        items.extend(extract_reddit(config))
    if "twitch" in sources:
        items.extend(extract_twitch(config))
    LOGGER.info("Extraction stage produced %s raw items", len(items))
    return items


def existing_hashes(raw_hashes: Iterable[str]) -> set[str]:
    """Fetch already-seen raw text hashes from PostgreSQL."""

    if db_pool is None:
        return set()

    from psycopg2 import Error as PsycopgError

    hashes = list(raw_hashes)
    if not hashes:
        return set()

    conn = db_pool.getconn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT raw_text_hash FROM slang_terms WHERE raw_text_hash = ANY(%s)",
                (hashes,),
            )
            return {row[0] for row in cursor.fetchall()}
    except PsycopgError:
        LOGGER.exception("Failed to query existing raw_text_hash values")
        return set()
    finally:
        db_pool.putconn(conn)


def split_chunks(text: str, max_chars: int = 512) -> list[str]:
    """Split long text into sentence-ish chunks no longer than max_chars."""

    if len(text) <= max_chars:
        return [text]

    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            chunks.extend(sentence[i : i + max_chars] for i in range(0, len(sentence), max_chars))
            continue
        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def build_embed_text(item: dict[str, Any]) -> str:
    """Build the text field that should be embedded for an item."""

    source = item.get("source")
    if source == "urban_dict":
        text = (
            f"Term: {item.get('term')}. "
            f"Definition: {item.get('definition')}. "
            f"Example: {item.get('example') or ''}"
        )
    elif source == "reddit":
        text = f"[r/{item.get('subreddit', '')}] {item.get('raw_text', '')}"
    elif source == "twitch":
        text = f"[Twitch #{item.get('channel', '')}] {item.get('raw_text', '')}"
    else:
        text = item.get("raw_text", "")
    return clean_text(text)[:512]


def transform_all(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Clean, deduplicate, chunk, and assign embedding IDs to raw items."""

    seen_hashes: set[str] = set()
    candidate_hashes = [
        text_hash(chunk)
        for item in raw_items
        for chunk in split_chunks(clean_text(item.get("raw_text", "")))
        if chunk
    ]
    stored_hashes = existing_hashes(candidate_hashes)
    transformed: list[dict[str, Any]] = []

    for item in raw_items:
        raw_text = clean_text(item.get("raw_text", ""))
        if not raw_text:
            LOGGER.debug("Skipping item with empty raw_text")
            continue

        for chunk in split_chunks(raw_text):
            chunk_hash = text_hash(chunk)
            if chunk_hash in seen_hashes or chunk_hash in stored_hashes:
                LOGGER.debug("Skipping duplicate raw_text_hash=%s", chunk_hash)
                continue
            seen_hashes.add(chunk_hash)

            transformed_item = dict(item)
            transformed_item["raw_text"] = chunk
            transformed_item["raw_text_hash"] = chunk_hash
            transformed_item["embedding_id"] = str(uuid.uuid4())
            transformed_item["embed_text"] = build_embed_text(transformed_item)
            transformed.append(transformed_item)

    LOGGER.info("Transform stage produced %s items", len(transformed))
    return transformed


def get_embedding_model() -> Any:
    """Load and return the embedding model exactly once per process."""

    global model
    if model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ConfigurationError(
                "Embedding requires sentence-transformers. Run: pip install -r requirements.txt"
            ) from exc

        LOGGER.info("Loading embedding model %s", MODEL_NAME)
        model = SentenceTransformer(MODEL_NAME)
    return model


def embed_all(items: list[dict[str, Any]], config: Config) -> list[dict[str, Any]]:
    """Generate normalized vector embeddings for transformed items."""

    if not items:
        return items

    embedding_model = get_embedding_model()
    batch_size = max(config.batch_size, 1)
    for start in range(0, len(items), batch_size):
        batch = items[start : start + batch_size]
        texts = [item["embed_text"] for item in batch]
        try:
            vectors = embedding_model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=True,
            )
            for item, vector in zip(batch, vectors, strict=True):
                item["vector"] = vector.tolist()
        except Exception:
            LOGGER.exception("Embedding batch failed; retrying items one by one")
            for item in batch:
                try:
                    vector = embedding_model.encode(
                        [item["embed_text"]],
                        normalize_embeddings=True,
                        show_progress_bar=False,
                    )[0]
                    item["vector"] = vector.tolist()
                except Exception:
                    item["vector"] = None
                    LOGGER.exception("Embedding failed for %s", item.get("embedding_id"))

        if start and start % 100 == 0:
            LOGGER.info("Embedded %s/%s items", start, len(items))

    embedded = sum(1 for item in items if item.get("vector") is not None)
    LOGGER.info("Embed stage generated %s/%s vectors", embedded, len(items))
    return items


def pinecone_metadata(item: dict[str, Any]) -> dict[str, Any]:
    """Build Pinecone metadata within practical size limits."""

    scraped_at = item.get("scraped_at")
    if isinstance(scraped_at, datetime):
        scraped_at_value = scraped_at.isoformat()
    elif scraped_at:
        scraped_at_value = isoparse(str(scraped_at)).isoformat()
    else:
        scraped_at_value = datetime.now(timezone.utc).isoformat()

    return {
        "term": item.get("term") or "",
        "source": item.get("source") or "",
        "subreddit": item.get("subreddit") or "",
        "channel": item.get("channel") or "",
        "raw_text": (item.get("raw_text") or "")[:1000],
        "upvotes": int(item.get("upvotes") or 0),
        "scraped_at": scraped_at_value,
    }


def upsert_pinecone(items: list[dict[str, Any]], config: Config) -> int:
    """Upsert embedded items to Pinecone in batches."""

    try:
        from pinecone import Pinecone
    except ImportError as exc:
        raise ConfigurationError("Pinecone loading requires pinecone-client. Run: pip install -r requirements.txt") from exc

    pc = Pinecone(api_key=config.pinecone_api_key)
    index = pc.Index(config.pinecone_index_name)
    upserted = 0

    vectors = [
        {
            "id": item["embedding_id"],
            "values": item["vector"],
            "metadata": pinecone_metadata(item),
        }
        for item in items
        if item.get("vector") is not None
    ]

    for start in range(0, len(vectors), 100):
        batch = vectors[start : start + 100]
        index.upsert(vectors=batch)
        upserted += len(batch)
        LOGGER.info("Pinecone upserted batch of %s vectors", len(batch))
        time.sleep(0.5)

    return upserted


def insert_postgres(items: list[dict[str, Any]]) -> int:
    """Insert item metadata into PostgreSQL idempotently."""

    if db_pool is None:
        raise RuntimeError("PostgreSQL pool is not initialized")

    from psycopg2 import Error as PsycopgError

    inserted = 0
    conn = db_pool.getconn()
    try:
        cursor = conn.cursor()
        try:
            for index, item in enumerate(items, start=1):
                try:
                    cursor.execute("SAVEPOINT harvester_insert")
                    cursor.execute(
                        """
                        INSERT INTO slang_terms (
                            term, source, definition, example, raw_text,
                            raw_text_hash, upvotes, downvotes, subreddit,
                            channel, author, scraped_at, embedding_id, is_embedded
                        )
                        VALUES (
                            %(term)s, %(source)s, %(definition)s, %(example)s,
                            %(raw_text)s, %(raw_text_hash)s, %(upvotes)s,
                            %(downvotes)s, %(subreddit)s, %(channel)s, %(author)s,
                            %(scraped_at)s, %(embedding_id)s, %(is_embedded)s
                        )
                        ON CONFLICT DO NOTHING
                        """,
                        {
                            "term": item.get("term") or "",
                            "source": item.get("source"),
                            "definition": item.get("definition"),
                            "example": item.get("example"),
                            "raw_text": item.get("raw_text"),
                            "raw_text_hash": item.get("raw_text_hash"),
                            "upvotes": int(item.get("upvotes") or 0),
                            "downvotes": int(item.get("downvotes") or 0),
                            "subreddit": item.get("subreddit"),
                            "channel": item.get("channel"),
                            "author": item.get("author"),
                            "scraped_at": item.get("scraped_at") or datetime.now(timezone.utc),
                            "embedding_id": item.get("embedding_id"),
                            "is_embedded": item.get("vector") is not None,
                        },
                    )
                    inserted += cursor.rowcount
                    cursor.execute("RELEASE SAVEPOINT harvester_insert")
                except PsycopgError:
                    cursor.execute("ROLLBACK TO SAVEPOINT harvester_insert")
                    cursor.execute("RELEASE SAVEPOINT harvester_insert")
                    LOGGER.exception("PostgreSQL insert failed for %s", item.get("embedding_id"))
                    continue

                if index % 50 == 0:
                    conn.commit()
                    LOGGER.info("PostgreSQL committed %s rows", index)
            conn.commit()
        finally:
            cursor.close()
    finally:
        db_pool.putconn(conn)

    return inserted


def load_all(items: list[dict[str, Any]], config: Config) -> tuple[int, int]:
    """Load embedded items into Pinecone and PostgreSQL."""

    loadable = [item for item in items if item.get("vector") is not None]
    skipped = len(items) - len(loadable)
    if not loadable:
        LOGGER.info("Load stage skipped because no vectors were available")
        return 0, skipped

    pinecone_count = upsert_pinecone(loadable, config)
    postgres_count = insert_postgres(loadable)
    success = min(pinecone_count, postgres_count)
    LOGGER.info(
        "Load stage complete: pinecone=%s postgres=%s skipped=%s",
        pinecone_count,
        postgres_count,
        skipped,
    )
    return success, skipped


def parse_terms(raw_terms: str | None) -> list[str]:
    """Parse CLI comma-separated terms or return default seed terms."""

    if not raw_terms:
        return SEED_TERMS
    terms = [term.strip() for term in raw_terms.split(",") if term.strip()]
    return terms or SEED_TERMS


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description="Run the slang ETL harvester.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract and transform only; do not embed, connect to databases, or write records.",
    )
    parser.add_argument("--source", choices=["urban", "reddit", "twitch"], help="Run only one source.")
    parser.add_argument("--terms", help='Comma-separated Urban Dictionary terms, e.g. "rizz,no cap,slay".')
    return parser.parse_args(argv)


def run_pipeline(args: argparse.Namespace, config: Config) -> tuple[int, int, int, int]:
    """Run extract, transform, embed, and load stages in order."""

    terms = parse_terms(args.terms)
    raw_items = extract_all(config, args.source, terms)
    transformed = transform_all(raw_items)

    if args.dry_run:
        LOGGER.info("Dry run complete after transform stage")
        return len(raw_items), len(transformed), 0, 0

    embedded = embed_all(transformed, config)
    success, skipped = load_all(embedded, config)
    return len(raw_items), len(transformed), success, skipped


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""

    setup_logging()
    start = time.monotonic()
    load_dotenv()
    print_setup_instructions()

    try:
        args = parse_args(argv)
        config = load_config()
        validate_env(config, args.source, args.dry_run)
        setup_database(config, args.dry_run)

        LOGGER.info("Pipeline start")
        raw_count, transformed_count, loaded_count, skipped_count = run_pipeline(args, config)
        elapsed = time.monotonic() - start
        LOGGER.info(
            "Pipeline complete: raw=%s transformed=%s loaded=%s skipped=%s elapsed=%.2fs",
            raw_count,
            transformed_count,
            loaded_count,
            skipped_count,
            elapsed,
        )
        return 0
    except ConfigurationError as exc:
        LOGGER.error("%s", exc)
        return 2
    except KeyboardInterrupt:
        LOGGER.warning("Interrupted")
        return 130
    except Exception:
        LOGGER.exception("Pipeline failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
