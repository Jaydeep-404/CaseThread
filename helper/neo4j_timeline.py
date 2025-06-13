import os
from neo4j import GraphDatabase
from typing import Any, Dict, List, Optional
from datetime import date
from neo4j.time import Date
from dotenv import load_dotenv
from uuid import uuid4
load_dotenv()

## Graphdb configuration
URI      = os.getenv("NEO4J_URI", "neo4j+s://localhost:7687")
USER     = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "password")  


def serialize_neo4j_value(value: Any):
    """Recursively convert Neo4j values to serializable types."""
    if hasattr(value, "isoformat"):
        return value.isoformat()  # handles neo4j.time.Date, datetime.date, datetime.datetime
    elif isinstance(value, list):
        return [serialize_neo4j_value(v) for v in value]
    elif isinstance(value, dict):
        return {k: serialize_neo4j_value(v) for k, v in value.items()}
    return value

    

# Get data from neo4j by case id
# def get_timeline_data_by_case_id(case_id: str, skip: int, limit: int, start_date, end_date):
#     filters = []
#     params = {
#         "case": case_id,
#         "skip": skip,
#         "limit": limit
#     }

#     if start_date:
#         filters.append("ev.date >= date($start_date)")
#         params["start_date"] = start_date.isoformat()
#     if end_date:
#         filters.append("ev.date <= date($end_date)")
#         params["end_date"] = end_date.isoformat()

#     where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

#     query = f"""
#         MATCH (c:Case {{name: $case}})-[:HAS_FILE]->(f:Source)-[:HAS_EVENT]->(ev:Event)
#         {where_clause}
#         OPTIONAL MATCH (ev)-[:INVOLVES]->(e:Entity)
#         RETURN f.name AS source,
#                ev.id AS eventId,
#                ev.date AS date,
#                ev.statement AS statement,
#                collect(e.name) AS entities
#         ORDER BY date
#         SKIP $skip
#         LIMIT $limit
#     """

#     count_query = f"""
#         MATCH (c:Case {{name: $case}})-[:HAS_FILE]->(f:Source)-[:HAS_EVENT]->(ev:Event)
#         {where_clause}
#         RETURN count(ev) AS total
#     """
 
#     with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as driver, driver.session() as session:
#         result = session.run(query, **params)
#         data = result.data()

#         count_result = session.run(count_query, **params)
#         total_items = count_result.single()["total"]

#     # Convert Neo4j Date to ISO string
#     for item in data:
#         if "date" in item and isinstance(item["date"], Date):
#             item["date"] = item["date"].iso_format()

#     return data, total_items


# # Get the timeline data by case id based on the unique date and the entity name
def get_timeline_data_by_case_id(case_id: str, skip: int, limit: int, start_date, end_date):
    try:
        filters = []
        params = {
            "case": case_id,
            "skip": skip,
            "limit": limit
        }

        if start_date:
            filters.append("ev.date >= date($start_date)")
            params["start_date"] = start_date.isoformat()
        if end_date:
            filters.append("ev.date <= date($end_date)")
            params["end_date"] = end_date.isoformat()

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

        query = f"""
            MATCH (c:Case {{name: $case}})-[:HAS_FILE]->(f:Source)-[:HAS_EVENT]->(ev:Event)-[:INVOLVES]->(e:Entity)
            {where_clause}
            WITH ev, f, collect(DISTINCT e.name) AS entityList
            WITH ev, f, apoc.coll.sort(entityList) AS sortedEntities
            WITH ev.date AS date,
                ev.id AS eventId,
                ev.statement AS statement,
                ev.category AS category,
                coalesce(ev.tag, '') AS tag,
                sortedEntities AS entities,
                f.name AS source,
                f.ingestedAt AS ingestedAt
            ORDER BY ingestedAt DESC
            WITH date, statement, category, tag, entities, collect({{
                eventId: eventId,
                statement: statement,
                category: category,
                tag: tag,
                source: source,
                ingestedAt: ingestedAt
            }})[0] AS latest
            RETURN latest.source AS source,
                latest.eventId AS eventId,
                date,
                latest.statement AS statement,
                latest.category AS category,
                latest.tag AS tag,
                entities
            ORDER BY date
            SKIP $skip
            LIMIT $limit
        """
        # query = f"""
        #     MATCH (c:Case {{name: $case}})-[:HAS_FILE]->(f:Source)-[:HAS_EVENT]->(ev:Event)-[:INVOLVES]->(e:Entity)
        #     {where_clause}
        #     WITH ev, f, collect(DISTINCT e.name) AS entityList,
        #          collect(DISTINCT {{name: e.name, type: e.type}}) AS entityWithTypeList
        #     WITH ev, f, apoc.coll.sort(entityList) AS sortedEntities,
        #          entityWithTypeList AS entitiesWithType
        #     WITH ev.date AS date,
        #          ev.id AS eventId,
        #          ev.statement AS statement,
        #          ev.category AS category,
        #          sortedEntities AS entities,
        #          entitiesWithType,
        #          f.name AS source,
        #          f.ingestedAt AS ingestedAt
        #     ORDER BY ingestedAt DESC
        #     WITH date, statement, category, entities, entitiesWithType, collect({{
        #          eventId: eventId,
        #          statement: statement,
        #          category: category,
        #          source: source,
        #          ingestedAt: ingestedAt
        #     }})[0] AS latest
        #     RETURN latest.source AS source,
        #            latest.eventId AS eventId,
        #            date,
        #            latest.statement AS statement,
        #            latest.category AS category,
        #            entities,
        #            entitiesWithType
        #     ORDER BY date DESC
        #     SKIP $skip
        #     LIMIT $limit
        # """

        count_query = f"""
            MATCH (c:Case {{name: $case}})-[:HAS_FILE]->(:Source)-[:HAS_EVENT]->(ev:Event)-[:INVOLVES]->(e:Entity)
            {where_clause}
            WITH ev, collect(DISTINCT e.name) AS entityList
            WITH ev.date AS date, ev.statement AS statement, ev.category AS category, coalesce(ev.tag, '') AS tag, apoc.coll.sort(entityList) AS sortedEntities
            WITH date, statement, category, sortedEntities,
                date + '|' + statement + '|' + category + '|' + tag + '|' + apoc.text.join(sortedEntities, ',') AS uniqueKey
            RETURN count(DISTINCT uniqueKey) AS total

        """

        with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as driver, driver.session() as session:
            result = session.run(query, **params)
            data = result.data()

            count_result = session.run(count_query, **params)
            total_items = count_result.single()["total"]

        # Convert Neo4j Date to ISO string
        for item in data:
            if "date" in item and isinstance(item["date"], Date):
                item["date"] = item["date"].iso_format()

        return data, total_items
    except Exception as e:
        print(f"Error in get_timeline_data_by_case_id: {e}")
        return [], 0


def delete_case_from_neo4j(case_id: str):
    """Delete the case, its files, and any orphan events/entities."""
    _DELETE_CASE = [
        # 1. remove all files under the case
        "MATCH (c:Case {name:$case})-[:HAS_FILE]->(f:Source) DETACH DELETE f",
        # 2. delete the case node
        "MATCH (c:Case {name:$case}) DETACH DELETE c",
        # 3. orphan sweeps
        "MATCH (ev:Event) WHERE NOT (ev)<-[:HAS_EVENT]-(:Source) DETACH DELETE ev",
        "MATCH (e:Entity) WHERE NOT (e)<-[:INVOLVES]-(:Event) DETACH DELETE e",
    ]
    with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as drv, drv.session() as s:
        n = r = 0
        for stmt in _DELETE_CASE:
            res = s.run(stmt, case=case_id).consume()
            n += res.counters.nodes_deleted
            r += res.counters.relationships_deleted
    print(f"🗑 CASE {case_id}: -{n} nodes, -{r} rels")
    


# Deleting file from neo4j
# def delete_file_from_neo4j(case_id: str, source: str):
#     _DELETE_FILE_IN_CASE = [
#         "MATCH (c:Case {name:$case})-[:HAS_FILE]->(f:Source {name:$source}) DETACH DELETE f",
#         "MATCH (ev:Event) WHERE NOT (ev)<-[:HAS_EVENT]-(:Source) DETACH DELETE ev",
#         "MATCH (e:Entity) WHERE NOT (e)<-[:INVOLVES]-(:Event) DETACH DELETE e",
#     ]
#     with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as drv, drv.session() as s:
#         nodes = rels = 0
#         for stmt in _DELETE_FILE_IN_CASE:
#             res = s.run(stmt, case=case_id, source=source).consume()
#             nodes += res.counters.nodes_deleted
#             rels += res.counters.relationships_deleted
#     print(f"Dleted from neo4j -{nodes} nodes, -{rels} rels")


def delete_file_from_neo4j(case_id: str, source: str):
    _DELETE_FILE_IN_CASE = [
        # Delete the Source node and its direct relationships
        "MATCH (c:Case {name:$case})-[:HAS_FILE]->(f:Source {name:$source}) DETACH DELETE f",

        # Delete Events no longer connected to any Source
        "MATCH (ev:Event) WHERE NOT (ev)<-[:HAS_EVENT]-(:Source) DETACH DELETE ev",

        # Delete Entities no longer connected to any Event
        "MATCH (e:Entity) WHERE NOT (e)<-[:INVOLVES]-(:Event) DETACH DELETE e",

        # Delete Year nodes no longer connected to any Event
        "MATCH (y:Year) WHERE NOT (y)<-[:HAPPENED_IN]-(:Event) DELETE y"
    ]

    with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as drv, drv.session() as s:
        nodes = rels = 0
        for stmt in _DELETE_FILE_IN_CASE:
            res = s.run(stmt, case=case_id, source=source).consume()
            nodes += res.counters.nodes_deleted
            rels += res.counters.relationships_deleted
            
            
# delete entity entity name
_CYPHER_DELETE_ENTITY_FROM_CASE = """
MATCH (e:Entity {case: $case, name: $entity})
DETACH DELETE e
"""

def delete_entity_from_case(case_id: str, entity_name: str):
    with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as drv, drv.session() as s:
        res = s.run(_CYPHER_DELETE_ENTITY_FROM_CASE, case=case_id, entity=entity_name).consume()
    print(f"Deleted entity '{entity_name}',from case '{case_id}': -{res.counters.nodes_deleted} node(s), -{res.counters.relationships_deleted} rel(s)")
    return res

    
_QUERY_ENTITY_IN_CASE = """
MATCH (c:Case {name:$case})-[:HAS_FILE]->(:File)-[:HAS_EVENT]->(ev)
MATCH (ev)-[:INVOLVES]->(:Entity {case:$case, name:$entity})
OPTIONAL MATCH (ev)-[:INVOLVES]->(co:Entity {case:$case})
OPTIONAL MATCH (file:File)-[:HAS_EVENT]->(ev)
RETURN ev.date AS date, ev.statement AS statement,
       collect(DISTINCT co.name)  AS coEntities,
       collect(DISTINCT file.name) AS sourceFiles
# ORDER BY date"""

def get_entity_in_case(case_name: str, entity_name: str):
    with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as drv, drv.session() as s:
        return s.run(_QUERY_ENTITY_IN_CASE, case=case_name, entity=entity_name).data()


async def get_entity_graph_echarts(case_name: str):
    """
    Return a dict with `nodes`, `links`, and `categories` for the specified case,
    formatted for ECharts graph visualization.
    """
    cypher = """
    // Collect categories dynamically and assign a numeric index to each
    MATCH (c:Case {name: $case})-[:HAS_FILE]->(:Source)-[:HAS_EVENT]->(ev:Event)
    WITH DISTINCT ev.category AS cat
    ORDER BY cat
    WITH collect(coalesce(cat, 'Uncategorised')) AS categoryList

    // Gather entity nodes with their category
    MATCH (c:Case {name: $case})-[:HAS_FILE]->(:Source)-[:HAS_EVENT]->(ev)-[:INVOLVES]->(e:Entity)
    WITH categoryList, ev, e, coalesce(ev.category, 'Uncategorised') AS cat
    WITH categoryList, e.name AS name, cat,
         apoc.coll.indexOf(categoryList, cat) AS catIndex,
         count(ev) AS involvementCount
    WITH categoryList, {
        id: name,
        name: name,
        value: toFloat(involvementCount),
        symbolSize: 10 + sqrt(toFloat(involvementCount)) * 5,
        category: catIndex
    } AS node
    WITH categoryList, collect(DISTINCT node) AS nodes

    // Build links (co-involvement in the same event)
    MATCH (c:Case {name: $case})-[:HAS_FILE]->(:Source)-[:HAS_EVENT]->(ev)-[:INVOLVES]->(a:Entity)
    MATCH (ev)-[:INVOLVES]->(b:Entity)
    WHERE a <> b AND a.name < b.name
    WITH categoryList, nodes,
         collect(DISTINCT {
             source: a.name,
             target: b.name
         }) AS links

    // Final assembly
    RETURN {
        nodes: nodes,
        links: links,
        categories: [cat IN categoryList | {name: cat}]
    } AS graph
    """

    with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as driver, driver.session() as session:
        result = session.run(cypher, case=case_name).single()
        if result:
            return result["graph"]
        return {"nodes": [], "links": [], "categories": []}
    
    
async def update_entity_and_event(driver, case_name, entity_name, new_name=None, new_statement=None, new_category=None):
    query = """
    MATCH (c:Case {name: $case_name})-[:HAS_FILE]->(:Source)-[:HAS_EVENT]->(ev:Event)-[:INVOLVES]->(e:Entity {name: $entity_name})
    WHERE e.case = $case_name
    FOREACH (_ IN CASE WHEN $new_name IS NOT NULL THEN [1] ELSE [] END |
      SET e.name = $new_name
    )
    FOREACH (_ IN CASE WHEN $new_statement IS NOT NULL THEN [1] ELSE [] END |
      SET ev.statement = $new_statement
    )
    FOREACH (_ IN CASE WHEN $new_category IS NOT NULL THEN [1] ELSE [] END |
      SET ev.category = $new_category
    )
    RETURN e, ev
    """
    async with driver.session() as session:
        result = await session.run(
            query,
            case_name=case_name,
            entity_name=entity_name,
            new_name=new_name,
            new_statement=new_statement,
            new_category=new_category,
        )
        record = await result.single()
        if record:
            return {
                "entity": record["e"],
                "event": record["ev"],
            }
        return None 
  

async def delete_entity(case_name, entity_name):
    query = """
    MATCH (c:Case {name: $case_name})-[:HAS_FILE]->(:Source)-[:HAS_EVENT]->(ev:Event)-[:INVOLVES]->(e:Entity {name: $entity_name})
    WHERE e.case = $case_name
    DETACH DELETE e
    """
    with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as driver, driver.session() as session:
        session.run(query, case_name=case_name, entity_name=entity_name)

    
# fetch graph data for echarts
async def fetch_graph_data_new(case_name: str, source_id: str) -> Dict[str, Any]:
    try:
        with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as drv, drv.session() as s:
            # 1️⃣ Fetch nodes (entities + their types)
            nodes_result = s.run("""
                MATCH (c:Case {name: $case})-[:HAS_FILE]->(f:Source)-[:HAS_EVENT]->(ev:Event)-[:INVOLVES]->(e:Entity)
                WHERE elementId(f) = $source_id
                RETURN DISTINCT e.name AS name, e.type AS type
            """, case=case_name, source_id=source_id)

            nodes = []
            name_to_id = {}
            id_counter = 0
            categories_set = set()

            for record in nodes_result:
                entity_name = record["name"]
                entity_type = record.get("type", "unknown") or "unknown"

                node_id = str(id_counter)
                id_counter += 1

                # Track for links mapping
                name_to_id[entity_name] = node_id

                # Track categories
                categories_set.add(entity_type)

                nodes.append({
                    "id": node_id,
                    "name": entity_name,
                    "category": entity_type,
                    "type": entity_type,
                    # Optional size, position (can be randomized or calculated on the frontend)
                    "symbolSize": 10
                })
                
            # 2️⃣ Fetch edges (relations)
            links_result = s.run("""
                MATCH (c:Case {name: $case})-[:HAS_FILE]->(f:Source)-[:HAS_EVENT]->(ev:Event)
                WHERE elementId(f) = $source_id
                MATCH (e1:Entity)-[r:REL {eventId: ev.id}]->(e2:Entity)
                RETURN DISTINCT e1.name AS source, e2.name AS target, r.relType AS relType
            """, case=case_name, source_id=source_id)

            links = []
            for record in links_result:
                source_name = record["source"]
                target_name = record["target"]

                # Only create links if both entities exist (in case of filter issues)
                if source_name in name_to_id and target_name in name_to_id:
                    links.append({
                        "source": name_to_id[source_name],
                        "target": name_to_id[target_name],
                        "relType": record["relType"]
                    })

            # 3️⃣ Build category list (for filter dropdown in the frontend)
            categories = [{"name": cat} for cat in sorted(categories_set)]

            # 4️⃣ Return in ECharts-friendly format
            return {
                "nodes": nodes,
                "links": links,
                "categories": categories
            }
    except Exception as e:
        print(f"Error fetching graph data: {e}")
        return {"nodes": [], "edges": [], "error": str(e)}
    

# fetch graph data for echarts
async def fetch_graph_data_new1(case_name: str) -> Dict[str, Any]:
    try:
        with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as drv, drv.session() as s:
            # 1️⃣ Fetch unique categories from the Events
            categories_result = s.run("""
                MATCH (c:Case {name: $case})-[:HAS_FILE]->(:Source)-[:HAS_EVENT]->(ev:Event)
                RETURN DISTINCT ev.category AS name
            """, case=case_name)

            categories = [{"name": record["name"]} for record in categories_result if record["name"]]
            category_names = {record["name"] for record in categories_result if record["name"]}

            # 2️⃣ Fetch nodes (entities + linked events with categories)
            nodes_result = s.run("""
                MATCH (c:Case {name: $case})-[:HAS_FILE]->(:Source)-[:HAS_EVENT]->(ev:Event)-[:INVOLVES]->(e:Entity)
                RETURN DISTINCT e.name AS name, ev.category AS category
            """, case=case_name)

            nodes = []
            name_to_id = {}
            id_counter = 0

            for record in nodes_result:
                entity_name = record["name"]
                category_name = record.get("category", "unknown") or "unknown"

                # Track for links mapping
                node_id = str(id_counter)
                id_counter += 1
                name_to_id[entity_name] = node_id

                nodes.append({
                    "id": node_id,
                    "name": entity_name,
                    "category": category_name,
                    "symbolSize": 10
                })

            # 3️⃣ Fetch edges (relations)
            links_result = s.run("""
                MATCH (c:Case {name: $case})-[:HAS_FILE]->(:Source)-[:HAS_EVENT]->(ev:Event)
                MATCH (e1:Entity)-[r:REL {eventId: ev.id}]->(e2:Entity)
                RETURN DISTINCT e1.name AS source, e2.name AS target, r.relType AS relType
            """, case=case_name)

            links = []
            for record in links_result:
                source_name = record["source"]
                target_name = record["target"]

                if source_name in name_to_id and target_name in name_to_id:
                    links.append({
                        "source": name_to_id[source_name],
                        "target": name_to_id[target_name],
                        "relType": record["relType"]
                    })

            # 4️⃣ Return data for ECharts
            return {
                "nodes": nodes,
                "links": links,
                "categories": categories
            }

    except Exception as e:
        print(f"Error fetching graph data: {e}")
        return {"nodes": [], "edges": [], "error": str(e)}



# fetch graph data for neo4j graph (with real deduplication)
async def fetch_graph_for_neo4j_graph_unique_relation(case_name: str, source_id: str) -> Dict[str, Any]:
    try:
        with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as drv, drv.session() as s:
            query = """
                MATCH (c:Case {name: $case})-[:HAS_FILE]->(f:Source)-[:HAS_EVENT]->(ev:Event)
                WHERE elementId(f) = $source_id

                MATCH (n:Entity)-[r:REL {eventId: ev.id}]-(m)
                WHERE (m:Year OR (m:Entity AND m.case = $case))
                WITH n, m, r.relType AS relType
                RETURN DISTINCT n, m, relType
            """
            result = s.run(query, case=case_name, source_id=source_id)

            nodes = []
            edges = []
            node_ids = set()
            edge_keys = set()

            for record in result:
                source = record["n"]
                target = record["m"]
                rel_type = record["relType"]

                source_id = str(source.id)
                target_id = str(target.id)

                # Source node
                if source_id not in node_ids:
                    nodes.append({
                        "id": source_id,
                        "label": source.get("name") or source_id
                    })
                    node_ids.add(source_id)

                # Target node
                if target_id not in node_ids:
                    nodes.append({
                        "id": target_id,
                        "label": target.get("name") or target_id
                    })
                    node_ids.add(target_id)

                # Deduplicate by (source, target, rel_type)
                edge_key = (source_id, target_id, rel_type)
                if edge_key not in edge_keys:
                    edges.append({
                        "from": source_id,
                        "to": target_id,
                        "label": rel_type,
                        "id": str(uuid4())
                    })
                    edge_keys.add(edge_key)

            return {"nodes": nodes, "edges": edges}

    except Exception as e:
        print(f"Error: {e}")
        return {"nodes": [], "edges": [], "error": str(e)}
   

    
# delete event from neo4j
async def delete_event_by_id(event_id: str):
    query = """
    MATCH (f:Source)-[he:HAS_EVENT]->(ev:Event)
    WHERE ev.id = $eventId
    DELETE he

    WITH ev, $eventId AS eid
    OPTIONAL MATCH (ev)<-[:HAS_EVENT]-(:Source)
    WITH ev, eid, count(*) AS stillLinked
    WHERE stillLinked = 0
    OPTIONAL MATCH ()-[re:REL {eventId: eid}]-()
    DELETE re
    DETACH DELETE ev

    WITH *
    MATCH (e:Entity)
    WHERE NOT (e)<-[:INVOLVES]-(:Event)
    DETACH DELETE e

    WITH *
    MATCH (y:Year)
    WHERE NOT ()-[:HAPPENED_IN]->(y)
    DETACH DELETE y
    """
    try:
        with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as driver, driver.session() as s:
            result = s.run(query, eventId=event_id)
            summary = result.consume()
            print("Deletion complete:", summary)
            return True
    except Exception as e:
        print(f"Error: {e}")
        return False
    
    
async def update_event_statement(event_id: str, new_statement: str):
    query = """
    MATCH (ev:Event {id: $eventId})
    SET ev.statement = $newStatement
    RETURN ev
    """
    try:
        with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as driver, driver.session() as s:
            result = s.run(query, eventId=event_id, newStatement=new_statement)
            record = result.single()
            if record:
                print("Updated statement for event:", record["ev"])
                return True
            else:
                print("Event not found")
                return False
    except Exception as e:
        print(f"Error: {e}")
        return False    


# # updare event in neo4j
# async def update_event_and_entities_in_neo4j(event_id: str, statement: str, entities: List[Dict[str, str]]) -> bool:
#     query_update_statement = """
#         MATCH (ev:Event {id: $event_id})
#         SET ev.statement = $statement
#     """

#     query_delete_old_relations = """
#         MATCH (ev:Event {id: $event_id})-[r:INVOLVES]->(e:Entity)
#         DELETE r
#     """

#     query_merge_entities_and_relations = """
#         UNWIND $entities AS entityData
#         MERGE (e:Entity {name: entityData.name, type: entityData.type})
#         WITH e
#         MATCH (ev:Event {id: $event_id})
#         MERGE (ev)-[:INVOLVES]->(e)
#     """

#     try:
#         with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as driver, driver.session() as session:
#             # Update event statement
#             session.run(query_update_statement, event_id=event_id, statement=statement)

#             # Remove old INVOLVES relations
#             session.run(query_delete_old_relations, event_id=event_id)

#             # Merge new entities and create INVOLVES relations
#             session.run(
#                 query_merge_entities_and_relations,
#                 event_id=event_id,
#                 entities=entities
#             )

#         return True
#     except Exception as e:
#         print("Error updating event and entities in Neo4j:", e)
#         return False


async def update_event_fields_in_neo4j(event_id: str, statement: Optional[str], category: Optional[str], date: Optional[str],  tag: Optional[str] ) -> bool:
    """
    Update only the statement, category, and date fields of an event in Neo4j.
    """

    query_update_event = """
        MATCH (ev:Event {id: $event_id})
        SET ev.statement = coalesce($statement, ev.statement),
            ev.category = coalesce($category, ev.category),
            ev.date = coalesce(date($date), ev.date),
            ev.tag       = coalesce($tag, ev.tag)
    """

    try:
        with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as driver, driver.session() as session:
            session.run(
                query_update_event,
                event_id=event_id,
                statement=statement,
                category=category,
                date=date,
                tag=tag
            )

        return True
    except Exception as e:
        print("Error updating event fields in Neo4j:", e)
        return False


async def get_sources_by_case(case_name: str) -> List[Dict[str, Any]]:
    try:
        with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as drv, drv.session() as s:
            result = s.run("""
                MATCH (c:Case {name: $case})-[:HAS_FILE]->(f:Source)
                RETURN elementId(f) AS sourceId, f.name AS sourceName
            """, case=case_name)
            
            return [dict(record) for record in result]
    except Exception as e:
        print(f"Error fetching source IDs: {e}")
        return []
