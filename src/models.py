from datetime import datetime
from pydantic import BaseModel


class Paper(BaseModel):
    entry_id: str
    title: str
    summary: str
    authors: str          # comma-joined
    categories: str       # comma-joined
    pdf_url: str
    submitted_at: datetime
    fetched_at: datetime
    expire_at: datetime


class GlossaryItem(BaseModel):
    term: str
    definition: str
    aliases: str = ""     # comma-separated synonyms
    first_seen_id: str = ""
    updated_at: datetime
