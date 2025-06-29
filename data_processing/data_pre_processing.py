import json
import re
import os
from fastapi import HTTPException
from dotenv import load_dotenv
from data_processing.data_parsing import parse_file
from data_processing.graph_db import neo4j_data_ingestor
from database import get_database
from data_processing.data_parsing import error_logger
from helper.scraper import scrape_content
from llama_index.llms.openai import OpenAI
from typing import Dict, Any, List
from datetime import datetime, timezone
load_dotenv


llm = OpenAI(
    model="gpt-4.1",
    # temperature=0.0,
    timeout=6000,
    additional_openai_params={
        "response_format": {"type": "json_object"}},
    api_key=os.getenv("OPENAI_API_KEY"),  
    )

async def pre_preocessing(text: str) -> List[Dict[str, Any]]:
    prompt = """**ROLE**  
    You are a forensic & financial analyst.

    **TASK**  
    From the TEXT → … section, extract **explicit or strongly implied calendar references** and produce a JSON list.  
    Each JSON object must have exactly these keys (case-sensitive):

    1. "Date" – Normalise to ISO:  
        • Day-month-year   → YYYY-MM-DD  
        • Month-year       → first day of that month (YYYY-MM-01)  
        • Quarter-year     → first day of the quarter (Q3 2024 → 2024-07-01)  
        • Year-only        → YYYY-01-01

    2. "Statement" – the single bullet or sentence that states the incident for that date.  
        • If a bullet contains several dates, **duplicate the bullet** so each object has one date.  
        • Preserve original wording, punctuation and capitalisation.

    3. "Entities" – distinct people, organisations, locations or products **mentioned in that statement**,  
       lower-case, alphabetically, separated by “; ”.  
        • Do not include dates, numbers or job titles.  
        • Ignore generic words (e.g., “company”, “group”, “co-operative”).

    4. "EntityTypes" – a list of entity types corresponding to each entity in "Entities",  
       e.g., ["person", "organization", "place"].  
       Possible values: "person", "organization", "place", "product", "other".

    5. "Relations" – for each entity pair, extract an explicit or **inferred** relationship from the statement,  
       using best judgment based on context.  
       Each relation is an object with:  
            • "Subject": entity name  
            • "Predicate": relationship/action verb or relational phrase, in lower-case snake_case  
            • "Object": entity name or year  
       For each pair of entities in the statement, **try to infer the most plausible relationship**,  
       even if it’s not directly stated.  
       If a relation is clearly not present for a pair, skip that pair.

    6. "Category" – one of:  
        • Business Activity | Biography | Legal | Governance | Financial Reporting | Event | Other  
        (If no bucket is an obvious fit, use “Other”).

    **RULES**  
    • If no entities are found in the statement, skip that statement entirely.  
    • Do not include duplicate JSON objects.  
    • Treat each list item, headline or bullet as a potential “sentence”.  
    • If the input text contains no qualifying statements, return an empty list `[]`.

    **Output specification**  
    Return only the JSON list, with no surrounding text, markdown or comments.

    TEXT →
    """
    prompt += "\n" + text

    response = await llm.acomplete(prompt)
    raw = response.text.strip()
    clean = re.sub(r"^```(?:json)?\n|\n```$", "", raw).strip()
    data = json.loads(clean)
    # print("data", data)
    return data


def clean_source(source: str) -> str:
    return re.sub(r"^uploads[\\/]", "", source)


async def process_data(db, limit=10):
    try:
        pending_docs = db.documents.find({
            "status": "pending",
            "is_md_file": True
        }).sort("created_at", 1).limit(limit)
        
        pending_docs_data = await pending_docs.to_list(length=limit)
        if not pending_docs_data:
            return False
        
        pending_ids = [doc["_id"] async for doc in pending_docs]
        # Step 2: Update them to "processing"
        if pending_ids:
            await db.documents.update_many(
                {"_id": {"$in": pending_ids}},
                {
                    "$set": {
                        "status": "processing",
                        "updated_at": datetime.now(timezone.utc)
                    }
                }
            )
        for doc in pending_docs_data:
            try:
                file_path = doc["md_file_path"]
                source_url = doc.get("document_url") if doc["document_type"] == 'link' else clean_source(doc['file_path'])
                case_id = doc.get("case_id")
                doc_title = doc.get("name", "Doc name")
                with open(file_path, 'r', encoding='utf-8') as f:
                    md_content = f.read()

                # Pre-processing extract entities
                json_data = await pre_preocessing(md_content)
                
                if not json_data:
                    err = "No entities found in the document."
                    await error_logger(db, doc["_id"], err) 
                    continue
                
                # Push to Neo4j with embbedding
                await neo4j_data_ingestor.push(case_id, source_url, doc_title, json_data)
                
                # wihout embbeding
                # push_to_neo4j(case_id, source_url, json_data)

                # store the processed data in MongoDB
                await db.time_line.insert_one({
                    "case_id": case_id,
                    "source_url": source_url,
                    "data": json_data
                })
                
                # Update document status
                await db.documents.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"status": "processed", "updated_at": datetime.now(timezone.utc)}}
                )

            except Exception as err:
                print(f"[ERROR] Failed processing document {doc.get('_id')}: {err}")
                # Update error status in MongoDB
                await error_logger(db, doc["_id"], err)

        return True
    except Exception as e:
        print("[FATAL ERROR] Processing failed:", e)
        return False
        

# Create markdown file from document
async def create_markdown_file(db, limit: int=10):
    try:
        document = db.documents.find({"is_md_file": {"$ne": True}, "status": "pending", "document_type": "file"}).sort("created_at", 1).limit(limit)
        pending_docs_data = await document.to_list(length=limit)
       
        if not pending_docs_data:
            print("No documents to process....")
            return "No documents to process"
        for doc in pending_docs_data:
            doc_id = doc["_id"]
            file_path = doc["file_path"]
            await parse_file(doc_id, file_path, db)
    except Exception as e:
        print("[FATAL ERROR] Creating markdown file failed:", e)
        return False
    

# Data ingestion pipeline
async def data_ingestion_pipeline(doc_type, limit: int=10):
    try:
        # Connect to MongoDB
        db = await get_database()
        
        if doc_type == 'link':
            # Scrape data from source
            await scrape_content(db, limit)
            print("Scraping task done")
        if doc_type == 'file':
            # create md files
            await create_markdown_file(db, limit)
            print("Markdown files create task done")
            
        # from markdown files to entities extraction and push to neo4j
        await process_data(db, limit)
        print("Data ingestion task done")
    except Exception as e:
        print("Data ingestion failed:", e)
        return False
        
