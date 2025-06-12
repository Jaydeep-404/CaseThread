from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import JSONResponse, Response
from models.timeline import PaginatedTimelineResponse, TimelineEntry, UpdateEventStatementRequest, EventUpdateRequest
from helper.neo4j_timeline import  get_timeline_data_by_case_id, update_entity_and_event, fetch_graph_data_new, fetch_graph_for_neo4j_graph_unique_relation, delete_event_by_id, update_event_statement, update_event_fields_in_neo4j
from typing import Optional, Dict, Any, List
from datetime import date
from routes.auth import get_current_user

# Initialize router
router = APIRouter()


# Get timeline data for a case
@router.get("/data/{case_id}", response_model=PaginatedTimelineResponse)
async def get_timeline(
    case_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    skip = (page - 1) * size
    try:
        data, total_count = get_timeline_data_by_case_id(case_id, skip, size, start_date, end_date)
        
        total_pages = (total_count + size - 1) // size
        data = [TimelineEntry(**e).serialize() for e in data]


        return PaginatedTimelineResponse(
            total_count=total_count,
            total_items=len(data),
            total_pages=total_pages,
            current_page=page,
            list=data
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entity-relation/{case_id}")
async def get_entities_with_relationships(case_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    try:
        data = await fetch_graph_data_new(case_id)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entity-neo4j-graph/{case_id}")
async def get_entities_data_for_neo4j_graph(case_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    try:
        print("case_id", case_id)
        data = await fetch_graph_for_neo4j_graph_unique_relation(case_id)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    
# Update event and entities in Neo4j
@router.put("/event/{event_id}")
async def update_event_and_entities(event_id: str, request: EventUpdateRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    try:
        success = await update_event_fields_in_neo4j(
            event_id=event_id,
            statement=request.statement,
            category=request.category,
            date=request.date
        )
        print("success", success)
        if success:
            return {"message": "Event updated successfully"}
        else:
            raise HTTPException(status_code=500, detail="Update failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# # Delete event from case
@router.delete("/{case_id}/event/{event_id}")
async def delete_event_from_timeline(case_id: str, event_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    try:
        res = await delete_event_by_id(event_id)
        if res:
            return Response(status_code=204)
        else:
            return JSONResponse(content={"message": "Event not found"}, status_code=404)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
