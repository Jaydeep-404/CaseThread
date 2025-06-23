import asyncio
from bson import ObjectId
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, BackgroundTasks, Query
from routes.auth import get_current_user
from helper.neo4j_timeline import delete_file_from_neo4j, delete_case_from_neo4j
from models.case import (
    CaseResponse, CaseUpdate, 
    DocumentCreate, DocumentResponse, DocumentUpdate,
    CaseStatus, DocumentStatus, PaginatedResponse, CaseCreate, PaginatedDocumentResponse
)
from database import get_database
from data_processing.data_pre_processing import clean_source, data_ingestion_pipeline
from dotenv import load_dotenv
load_dotenv()


router = APIRouter()

# Create uploads directory if it doesn't exist
UPLOAD_DIR = Path("./uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# Allowed file types
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",  # DOC
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # DOCX
    # "text/csv",   
    "text/plain"
}

MAX_FILE_SIZE_MB = 4  # 4MB limit
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024  # Convert MB to Bytes
MAX_FILES_ALLOWED = 4  # Maximum files allowed


# def generate_case_id():
#     """Generate a unique case ID with prefix and timestamp."""
#     timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
#     random_part = str(uuid.uuid4())[:8]
#     return f"CASE-{timestamp}-{random_part}"


        
@router.post("/", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(case_data: CaseCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db = Depends(get_database)
):
    """Create a new case with optional initial document."""
    # Unpack data
    name = case_data.name
    case_id = case_data.case_id
    
    if len(case_id) > 20:
        raise HTTPException(status_code=422, detail="Case ID must be at most 20 characters long")
    
    # Check if case already exists with same name or case_id
    existing_case = await db.cases.find_one({
        "user_id": str(current_user["_id"]),
        "$or": [
            {"name": name},
            {"case_id": case_id}
        ]
    })

    if existing_case:
        raise HTTPException(
            status_code=400,
            detail="A case with the same name or case id already exists."
        )
    
    # Create case
    case_data = {
        "user_id": str(current_user["_id"]),
        "case_id": case_data.case_id,
        "name": case_data.name,
        "description": case_data.description,
        "status": CaseStatus.ONGOING,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    
    # Insert case into database
    case_result = await db.cases.insert_one(case_data)
    case_object_id = str(case_result.inserted_id)
    
    # Prepare response
    case_response = {
        "id": case_object_id,
        "case_id": case_data["case_id"],
        "name": case_data["name"],
        "description": case_data["description"],
        "status": case_data["status"],
        "created_at": case_data["created_at"],
        "updated_at": case_data["updated_at"],
    }
    
    return CaseResponse(**case_response)


# Helper function to validate file size
def format_file_size(size_in_bytes: int) -> str:
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 ** 2:
        return f"{size_in_bytes / 1024:.2f} KB"
    elif size_in_bytes < 1024 ** 3:
        return f"{size_in_bytes / (1024 ** 2):.2f} MB"
    else:
        return f"{size_in_bytes / (1024 ** 3):.2f} GB"


@router.post("/{case_id}/documents", response_model=List[DocumentResponse])
async def upload_documents(
    case_id: str,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db = Depends(get_database)
):
    """Upload multiple documents to a case."""
    # Check if case exists
    case = await db.cases.find_one({"_id": ObjectId(case_id), "user_id": str(current_user["_id"])})
    print('case_name', case['name'])
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found"
        )
    
    # check the length of the files
    if len(files) > 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail= f"You can only upload up to {MAX_FILES_ALLOWED} files at a time"
        )
        
    uploaded_documents = []    
    for file in files:
        # vlidate the file type
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file type"
            )

         # Validate file size
        file_size = 0
        contents = b""
        for chunk in iter(lambda: file.file.read(4096), b""):
            file_size += len(chunk)
            if file_size > MAX_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail= f"File size exceeds the maximum allowed size {MAX_FILE_SIZE_MB} MB"
                )
            contents += chunk
            
        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty file is not allowed"
            )
        # Create unique filename
        file_extension = os.path.splitext(file.filename)[1] if file.filename else ""
        unique_filename = f"doc_{case_id}_{file.filename}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)
        
        # Save file
        with open(file_path, "wb") as buffer:
            buffer.write(contents)
        
        # Create document record
        document_data = {
            "case_id": case_id,
            "case_name": case['name'],
            "name": file.filename,
            "document_type": 'file',
            "file_path": file_path,
            "file_size": format_file_size(file_size),
            "content_type": file.content_type,
            "file_extension": file_extension,
            "status": DocumentStatus.PENDING,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        
        alredy_exist = await db.documents.find_one({"case_id": case_id, "name": file.filename})
        
        if alredy_exist:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File with name '{}' already exists".format(file.filename)
            )
        
        # Insert document into database
        document_result = await db.documents.insert_one(document_data)
        document_id = str(document_result.inserted_id)
        
        # Get document for response
        document = await db.documents.find_one({"_id": document_result.inserted_id})
        document["id"] = document_id
        del document["_id"]
        uploaded_documents.append(DocumentResponse(**document))

        # Schedule background task to parse the document
        # background_tasks.add_task(data_ingestion_pipeline)
   
        asyncio.create_task(data_ingestion_pipeline())
    return uploaded_documents


@router.post("/{case_id}/documents/link", response_model=DocumentResponse)
async def link_document(
    case_id: str,
    background_tasks: BackgroundTasks,
    document: DocumentCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db = Depends(get_database),
):
    """Link an external document (URL) to a case."""
    # Check if case exists
    case = await db.cases.find_one({"_id": ObjectId(case_id), "user_id": str(current_user["_id"])})
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found"
        )
    
    document_url = str(document.document_url)
    
    # Validate document URL is provided
    if not document.document_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="document_url is required to link an external document"
        )
    
    # check if document already exists
    existing_document = await db.documents.find_one({"case_id": case_id, "document_url": document_url})
    if existing_document:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document with URL '{}' already exists".format(document_url))
            
    # Create document record
    document_data = document.model_dump()
    document_data["case_id"] = case_id
    document_data["document_type"] = 'link'
    document_data['document_url'] = document_url
    document_data["case_name"] = case["name"]
    document_data["status"] = DocumentStatus.PENDING
    document_data["created_at"] = datetime.now(timezone.utc)
    document_data["updated_at"] = datetime.now(timezone.utc)
    
    # Insert document into database
    document_result = await db.documents.insert_one(document_data)
    document_id = str(document_result.inserted_id)
    
    # Get document for response
    created_document = await db.documents.find_one({"_id": document_result.inserted_id})
    created_document["id"] = document_id
    del created_document["_id"]
    
    # Scrape content from the URL
    # background_tasks.add_task(data_ingestion_pipeline)
    
    # Trigger background task if not already running
    asyncio.create_task(data_ingestion_pipeline())
    return DocumentResponse(**created_document)


@router.get("/", response_model=PaginatedResponse)
async def get_cases(
    status: Optional[str] = None,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=50, description="Page size"),
    sort: Optional[str] = None,
    search_value: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db = Depends(get_database)
):
    """
    Get cases with optional filtering, pagination, and sorting.

    - **status**: Filter by case status (open, in_progress, closed, archived)
    - **page**: Page number (starts at 1)
    - **size**: Number of records per page (max 50)
    """
    # Validate pagination params
    skip = (page - 1) * size
    user_id = str(current_user.get("_id"))
    
    # Build match stage
    match_stage: dict = {"user_id": user_id}
    if status and status != 'all':
        match_stage["status"] = status
    
    empty_list_response = {
        "list": [],
        "total_count": 0,
        "current_page": page,
        "total_items": 0,
        "total_pages": 0
        }
    # Validate status manually
    valid_statuses = {e.value for e in CaseStatus}
    if status and status not in valid_statuses:
        # Return a custom "no data found" response
        return empty_list_response

    # Add search conditions
    if search_value:
        or_conditions = [
            {"name": {"$regex": search_value, "$options": "i"}},
            {"case_id": {"$regex": search_value, "$options": "i"}}
        ]
        match_stage = {
            "$and": [
                match_stage,
                {"$or": or_conditions}
            ]
        }

    # Total count
    total_count = await db.cases.count_documents(match_stage)
    if total_count == 0:
        return empty_list_response
        # raise HTTPException(status_code=404, detail="No cases found")

    total_pages = (total_count + size - 1) // size

    # Sort stage
    # sort_order = -1 if sort is None else -1  # default to descending
    # sort_stage = {"updated_at": -1} if sort is None else {sort: sort_order}
    
    
    if sort == "alpha":
        sort_stage = {"name": 1}
    elif sort == "newest":
        sort_stage = {"updated_at": -1}
    elif sort == "oldest":
        sort_stage = {"created_at": 1}
    else:
        sort_stage = {"updated_at": -1}
        
    # Aggregation pipeline  
    pipeline = [
        {"$match": match_stage},
        {"$sort": sort_stage},
        {"$skip": skip},
        {"$limit": size},
        {"$addFields": {"case_id_str": {"$toString": "$_id"}}},
        {"$lookup": {
            "from": "documents",
            "localField": "case_id_str",
            "foreignField": "case_id",
            "as": "documents_array"
        }},
        {"$addFields": {
            "id": "$case_id_str",
            "document_count": {"$size": "$documents_array"}
        }},
        {"$project": {
            "_id": 0,
            "id": 1,
            "case_id": 1,
            "name": 1,
            "description": 1,
            "status": 1,
            "created_at": 1,
            "updated_at": 1,
            "document_count": 1
        }}
    ]

    # Execute aggregation
    cases = []
    async for doc in db.cases.aggregate(pipeline):
        cases.append(CaseResponse(**doc))

    # Return paginated response
    return {
        "list": cases,
        "total_count": total_count,
        "current_page": page,
        "total_items": size,
        "total_pages": total_pages
    }


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db = Depends(get_database)
):
    """Get a specific case by ID without documents."""
    
    pipeline = [
        {"$match": {"_id": ObjectId(case_id), "user_id": str(current_user.get("_id"))}},
        {"$addFields": {"case_id_str": {"$toString": "$_id"}}},
        {"$lookup": {
            "from": "documents",
            "localField": "case_id_str",
            "foreignField": "case_id",
            "as": "documents_array"
        }},
        {"$addFields": {
            "id": "$case_id_str",
            "document_count": {"$size": "$documents_array"}
        }},
        {"$project": {
            "_id": 0,
            "id": 1,
            "case_id": 1,
            "name": 1,
            "description": 1,
            "status": 1,
            "created_at": 1,
            "updated_at": 1,
            "document_count": 1  
        }}
    ]

    # Execute the pipeline
    case = None
    async for result in db.cases.aggregate(pipeline):
        case = result
        break

    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found"
        )

    return CaseResponse(**case)


@router.get("/{case_id}/documents", response_model=PaginatedDocumentResponse)
async def get_case_documents(
    case_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=50, description="Page size"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db = Depends(get_database)
):
    """
    Get all documents related to a specific case with pagination.
    """
    # Validate case existence
    case_exists = await db.cases.find_one({"_id": ObjectId(case_id), "user_id": str(current_user["_id"])})
    if not case_exists:
        raise HTTPException(status_code=404, detail="Case not found")

    # Count total documents
    total_count = await db.documents.count_documents({"case_id": case_id})
    total_pages = (total_count + size - 1) // size
    # Apply pagination
    skip = (page - 1) * size
    documents_cursor = db.documents.find({"case_id": case_id}).sort('created_at', -1).skip(skip).limit(size)

    # Fetch and serialize
    documents = []
    async for doc in documents_cursor:
        doc["id"] = str(doc["_id"])
        doc['file_path'] = f"{BASE_URL}/{doc['file_path']}" if doc['document_type'] == 'file' else None
        del doc["_id"]
        documents.append(DocumentResponse(**doc))

    return {
        "list": documents,
        "total_count": total_count,
        "current_page": page,
        "total_items": size,
        "total_pages": total_pages
    }


@router.put("/{case_id}", response_model=CaseResponse)
async def update_case(
    case_id: str,
    case_update: CaseUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db = Depends(get_database)
):
    """
    Update a case without returning documents.
    Checks if another case with the same name already exists.
    """
    user_id = str(current_user["_id"])

    # Check if case exists and belongs to user
    case = await db.cases.find_one({"_id": ObjectId(case_id), "user_id": user_id})
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found or you do not have permission to update this case."
        )

    # Prepare update data
    update_data = {
        k: v for k, v in case_update.model_dump(exclude_unset=True).items() if v is not None
    }

    # Duplicate check only for name
    if "name" in update_data:
        existing = await db.cases.find_one({
            "user_id": user_id,
            "name": update_data["name"],
            "_id": {"$ne": ObjectId(case_id)}
        })
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Another case with the same name already exists."
            )

    # Apply update
    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc)
        await db.cases.update_one(
            {"_id": ObjectId(case_id)},
            {"$set": update_data}
        )

    # Fetch updated case without documents
    pipeline = [
        {"$match": {"_id": ObjectId(case_id)}},
        {"$addFields": {"id": {"$toString": "$_id"}}},
        {"$project": {
            "_id": 0,
            "id": 1,
            "case_id": 1,
            "name": 1,
            "description": 1,
            "status": 1,
            "created_at": 1,
            "updated_at": 1
        }}
    ]

    updated_case = None
    async for result in db.cases.aggregate(pipeline):
        updated_case = result
        break

    if not updated_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found or update failed"
        )

    return CaseResponse(**updated_case)


@router.put("/{case_id}/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    case_id: str,
    document_id: str,
    document_update: DocumentUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db = Depends(get_database)
):
    """
    Update a document with a full update (PUT).
    This replaces the specified fields with new values.
    """
    # Check if document exists and belongs to the case
    document = await db.documents.find_one({
        "_id": ObjectId(document_id),
        "case_id": case_id
    })
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or does not belong to the specified case"
        )
    
    # Update fields that are provided
    update_data = {k: v for k, v in document_update.model_dump(exclude_unset=True).items() if v is not None}
    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc)
        await db.documents.update_one(
            {"_id": ObjectId(document_id)},
            {"$set": update_data}
        )
    
    # Get updated document
    updated_document = await db.documents.find_one({"_id": ObjectId(document_id)})
    updated_document["id"] = document_id
    del updated_document["_id"]
    
    return DocumentResponse(**updated_document)


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(
    case_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db = Depends(get_database)
):
    """Delete a case and all its documents."""
    # Check if case exists
    case = await db.cases.find_one({"_id": ObjectId(case_id), "user_id": str(current_user["_id"])})
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found"
        )
    
    # Get documents to delete files
    async for document in db.documents.find({"case_id": case_id}):
        if "file_path" in document:
            file_path = Path("." + document["file_path"])
            if file_path.exists():
                file_path.unlink()
    
    # Delete documents
    await db.documents.delete_many({"case_id": case_id})
    
    # Delete case
    await db.cases.delete_one({"_id": ObjectId(case_id)})
    
    # Delete case from neo4j
    delete_case_from_neo4j(case_id)
    return None


@router.delete("/{case_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    case_id: str,
    document_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db = Depends(get_database)
):
    """Delete a document."""
    # Check if document exists and belongs to the case
    document = await db.documents.find_one({
        "_id": ObjectId(document_id),
        "case_id": case_id
    })
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or does not belong to the specified case"
        )
    
    # Delete file if exists
    if "file_path" in document:
        file_path = Path("." + document["file_path"])
        if file_path.exists():
            file_path.unlink()
    
    # Delete document
    await db.documents.delete_one({"_id": ObjectId(document_id)})
    
    # Delete case fron neo4j   
    source = document.get("document_url") if document["document_type"] == 'link' else clean_source(document['file_path'])
    delete_file_from_neo4j(case_id, source)
    
    return None

