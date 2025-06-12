from llama_parse import LlamaParse
import os
from dotenv import load_dotenv
from bson import ObjectId

load_dotenv()

parser = LlamaParse(
    result_type="markdown",
    use_vendor_multimodal_model=True,
    # vendor_multimodal_model_name= os.getenv("VENDOR_MULTIMODAL_MODEL_NAME"),
    # vendor_multimodal_api_key= os.getenv("OPENAI_API_KEY"),
    api_key=os.getenv("LLAMA_CLOUD_API_KEY"),
    show_progress=False)


async def error_logger(db, doc_id, err):
    db.documents.update_one(
        {"_id": doc_id},
        {"$set": {"status": "error", "actual_error": str(err)}}
    )
    

async def parse_file(doc_id, file_path, db):
    try:
        document_objects = await parser.aload_data(file_path)
        text = ""
        for i in document_objects:
            text+=i.text
        
        output_file_path = f"./case_docs/doc_{doc_id}.md"
        
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write(text)
            
        # Update the document status
        await update_md_file_status(doc_id, output_file_path, db)
        
        return {"status": True, "message": "Data scraped"}
    except Exception as e:
        print(e)  
        await error_logger(db, doc_id, e)
        return {"status": False, "message": "Somthing went wrong"}
    

async def update_md_file_status(doc_id, output_file_path, db):
    try:
        db.documents.update_one({"_id": ObjectId(doc_id)},
                          {"$set": {"is_md_file": True, "md_file_path": output_file_path}})
        return True
    except Exception as e:
        print(e)
        return False

