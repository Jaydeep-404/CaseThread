from pydantic import BaseModel, Field, ConfigDict, HttpUrl
from typing import Optional, List
from datetime import datetime, date
from enum import Enum


class CaseStatus(str, Enum):
    """Case status enum"""
    ALL = "all"
    ONGOING = "ongoing"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"
    ARCHIVED = "archived"

class DocumentStatus(str, Enum):
    """Document status enum"""
    PENDING = "pending"
    PROCESSED = "processed"
    REJECTED = "rejected"
    ERROR = "error"

class DocumentBase(BaseModel):
    """Base document model"""
    name: str = Field(description="Document name")
    document_url: Optional[HttpUrl] = Field(None, description="URL to an external document")
    document_type: Optional[str] = Field(None, description="Type of the document")

class DocumentCreate(DocumentBase):
    """Document creation model"""
    pass

class DocumentInDB(DocumentBase):
    """Document in database model"""
    id: Optional[str] = Field(None, alias="_id")
    case_id: str = Field(description="ID of the associated case")
    file_url: Optional[str] = Field(None, description="URL to the file if uploaded")
    # file_name: Optional[str] = Field(None, description="Original filename")
    content_type: Optional[str] = Field(None, description="MIME type of the file")
    status: DocumentStatus = Field(default=DocumentStatus.PENDING)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "_id": "60d21b4967d0d8992e610c85",
                "name": "Identification Document",
                "document_url": "https://example.com/documents/id_card",
                "document_type": "id_card",
                "case_id": "60d21b4967d0d8992e610c86",
                "file_url": "https://example.com/files/id_card.pdf",
                "file_name": "id_card.pdf",
                "content_type": "application/pdf",
                "status": "pending",
                "created_at": "2021-06-22T12:00:00",
                "updated_at": "2021-06-22T12:00:00"
            }
        }
    )

class DocumentResponse(DocumentBase):
    """Document response model"""
    id: str
    case_id: str
    source: Optional[str] = None
    file_size: Optional[str] = None
    content_type: Optional[str] = None
    file_path: Optional[str] = None
    file_extension: Optional[str] = None
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime
    
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "60d21b4967d0d8992e610c85",
                "name": "Identification Document",
                "document_url": "https://example.com/documents/id_card",
                "document_type": "id_card",
                "case_id": "60d21b4967d0d8992e610c86",
                "file_url": "https://example.com/files/id_card.pdf",
                "file_name": "id_card.pdf",
                "content_type": "application/pdf",
                "status": "pending",
                "created_at": "2021-06-22T12:00:00",
                "updated_at": "2021-06-22T12:00:00"
            }
        }
    )

class CaseBase(BaseModel):
    """Base case model"""
    name: str 
    description: Optional[str] = Field(None, description="Case description")

class CaseCreate(CaseBase):
    """Case creation model"""
    case_id: str = Field(None, description="Unique case identifier")

class CaseInDB(CaseBase):
    """Case in database model"""
    id: Optional[str] = Field(None, alias="_id")
    case_id: str = Field(description="Unique case identifier")
    status: CaseStatus = Field(default=CaseStatus.ONGOING)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "_id": "60d21b4967d0d8992e610c86",
                "name": "Insurance Claim",
                "description": "Auto insurance claim for accident on May 10",
                "case_id": "CASE-2023-001",
                "status": "open",
                "created_at": "2021-06-22T12:00:00",
                "updated_at": "2021-06-22T12:00:00"
            }
        }
    )

class CaseResponse(CaseBase):
    """Case response model"""
    id: str
    case_id: str
    status: CaseStatus
    created_at: datetime
    updated_at: datetime
    document_count: Optional[int] = 0
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "60d21b4967d0d8992e610c86",
                "name": "Insurance Claim",
                "description": "Auto insurance claim for accident on May 10",
                "case_id": "CASE-2023-001",
                "status": "open",
                "created_at": "2021-06-22T12:00:00",
                "updated_at": "2021-06-22T12:00:00",
                "document_count": 2,
            }
        }
    )

class CaseUpdate(BaseModel):
    """Case update model"""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[CaseStatus] = None
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Updated Insurance Claim",
                "description": "Updated description",
                "status": "in_progress"
            }
        }
    )

class DocumentUpdate(BaseModel):
    """Document update model"""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[DocumentStatus] = None
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Updated Document Name",
                "description": "Updated description",
                "status": "verified"
            }
        }
    )

class PaginatedResponse(BaseModel):
    """Paginated response model"""
    list: List[CaseResponse]
    total_count: int
    current_page: int
    total_items: int
    total_pages: int
    
    class Config:
        alias_generator = lambda string: ''.join(
            word.capitalize() if i else word for i, word in enumerate(string.split('_'))
        )
        populate_by_name = True
        json_encoders = {
            # Optional: for ObjectId and datetime if needed
        }


class PaginatedDocumentResponse(BaseModel):
    """Paginated response model"""
    list: List[DocumentResponse]
    total_count: int
    current_page: int
    total_items: int
    total_pages: int
    
    class Config:
        alias_generator = lambda string: ''.join(
            word.capitalize() if i else word for i, word in enumerate(string.split('_'))
        )
        populate_by_name = True
        json_encoders = {
            # Optional: for ObjectId and datetime if needed
        }