from __future__ import annotations

import os
from typing import Iterable

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne


DEFAULT_DATABASE = "slang_db"
DEFAULT_COLLECTION = "wikipedia_2020s_slang"


def insert_records(
    records: Iterable[dict[str, str]],
    mongo_uri: str | None = None,
    database_name: str = DEFAULT_DATABASE,
    collection_name: str = DEFAULT_COLLECTION,
) -> int:
    """Insert or update slang records in MongoDB when a connection is configured."""
    load_dotenv()
    mongo_uri = mongo_uri or os.getenv("MONGODB_URI")
    if not mongo_uri:
        print("MONGODB_URI is not configured; skipping MongoDB insertion.")
        return 0

    operations = [
        UpdateOne({"term": record["term"], "source": record["source"]}, {"$set": record}, upsert=True)
        for record in records
    ]
    if not operations:
        return 0

    with MongoClient(mongo_uri) as client:
        result = client[database_name][collection_name].bulk_write(operations, ordered=False)
        return int(result.upserted_count + result.modified_count)
