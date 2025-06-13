import os
import re
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

class TimelineEntry(BaseModel):
    source: str
    eventId: str
    date: Optional[str]= ""
    statement: Optional[str] = ""
    category: Optional[str] = ""
    entities: List[str] = ""
    tag: Optional[str]= ""
    # entityWithTypeList: Optional[List[str]]
    
    def serialize(self):
        source_cleaned = self.source or ""

        # Add file path prefix if it starts with 'doc_'
        if source_cleaned.startswith("doc_"):
            source_cleaned = f"{BASE_URL}/uploads/{source_cleaned}"

        return {
            "eventId": self.eventId,
            "source": source_cleaned,
            "date": self.date,
            "statement": self.statement,
            "entities": self.entities,
            "category": self.category,
            "tag": self.tag
            # "entityWithTypeList": self.entityWithTypeList
        }



class PaginatedTimelineResponse(BaseModel):
    list: List[TimelineEntry]
    total_count: int
    total_items: int
    total_pages: int
    current_page: int
    
    class Config:
        alias_generator = lambda string: ''.join(
            word.capitalize() if i else word for i, word in enumerate(string.split('_'))
        )
        populate_by_name = True
        json_encoders = {
            # Optional: for ObjectId and datetime if needed
        }


class UpdateEventStatementRequest(BaseModel):
    statement: str
    

class EntityUpdate(BaseModel):
    name: str
    type: str


class EventUpdateRequest(BaseModel):
    statement: Optional[str] = None
    category: Optional[str] = None
    date: Optional[str] = None
    tag: Optional[str] = None
    # entities: List[EntityUpdate]