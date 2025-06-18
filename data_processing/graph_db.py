import re
import os, hashlib
import pandas as pd
from datetime import datetime, timezone
from typing import List, Dict, Any
from neo4j import GraphDatabase, ResultSummary
from openai import OpenAI, AsyncOpenAI
from neo4j import AsyncGraphDatabase

## Graphdb configuration
URI      = os.getenv("NEO4J_URI", "neo4j+s://localhost:7687")
USER     = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "password")  


_CONSTRAINT_STATEMENTS = [
    """CREATE CONSTRAINT case_name_unique IF NOT EXISTS\nFOR (c:Case) REQUIRE c.name IS UNIQUE""",
    """CREATE CONSTRAINT source_unique IF NOT EXISTS\nFOR (f:Source) REQUIRE f.name IS UNIQUE""",
    """CREATE CONSTRAINT event_id_unique IF NOT EXISTS\nFOR (ev:Event) REQUIRE ev.id IS UNIQUE""",
    """CREATE CONSTRAINT entity_name_unique IF NOT EXISTS\nFOR (e:Entity) REQUIRE e.name IS UNIQUE""",
    """CREATE INDEX event_date IF NOT EXISTS\nFOR (ev:Event) ON (ev.date)""",
]

def ensure_constraints() -> None:
    """Create constraints / indexes exactly once; safe to rerun."""
    with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as drv, drv.session() as s:
        for stmt in _CONSTRAINT_STATEMENTS:
            s.run(stmt)
    print("✅ Constraints ensured (safe to run repeatedly)")


# _CYPHER_PUSH = """
# MERGE (c:Case {name:$case})
# MERGE (f:Source {case:$case, name:$source})
#   ON CREATE SET f.ingestedAt = datetime($ingestedAt)
# MERGE (c)-[:HAS_FILE]->(f)
# WITH f, $rows AS rows, $case AS caseName
# UNWIND rows AS row
# MERGE (ev:Event {id:row.evId})
#   ON CREATE SET ev.date = date(row.date), 
#   ev.statement = row.statement, ev.category=row.category
# MERGE (f)-[:HAS_EVENT]->(ev)
# WITH ev, row, caseName
# UNWIND row.entities AS entName
# MERGE (e:Entity {case:caseName, name:entName})
# MERGE (ev)-[:INVOLVES]->(e);
# """

# def _hash_event(case_n: str, d: str, stmt: str) -> str:
#     return hashlib.sha256(f"{case_n}|{d}|{stmt}".encode()).hexdigest()

# def _prep_row(case_n: str, rec: Dict[str, str]) -> Dict:
#     return {
#         "evId": _hash_event(case_n, rec["Date"], rec["Statement"]),
#         "date": rec["Date"],
#         "statement": rec["Statement"],
#         "category": rec.get("Category", "Uncategorised"),
#         "entities": [e.strip() for e in rec["Entities"].split(";") if e.strip()],
#     }

# def push_to_neo4j(case_name: str, source: str, records: List[Dict[str, str]]) -> ResultSummary:
#     rows = [_prep_row(case_name, r) for r in records]
#     with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as drv, drv.session() as s:
#         res = s.run(
#             _CYPHER_PUSH,
#             case=case_name,
#             source=source,
#             ingestedAt=datetime.now(timezone.utc).isoformat(),
#             rows=rows,
#         ).consume()
#     print(f" {source}: +{res.counters.nodes_created} nodes, +{res.counters.relationships_created} rels")
#     return res


# _YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

# def _extract_years(text: str) -> List[int]:
#     return [int(m.group()) for m in _YEAR_RE.finditer(text)]

# def _hash_event(case_name: str, date: str, stmt: str) -> str:
#     return hashlib.sha256(f"{case_name}|{date}|{stmt}".encode()).hexdigest()

# ###############################################################################
# # 4️⃣ Row preparation                                                         #
# ###############################################################################

# def _prep_row(case_name: str, rec: Dict[str, Any]) -> Dict[str, Any]:
#     years     = _extract_years(rec["Statement"])
#     entities  = [e.strip() for e in rec["Entities"].split(";") if e.strip()]
#     relations = rec.get("Relations", [])
#     return {
#         "evId":      _hash_event(case_name, rec["Date"], rec["Statement"]),
#         "date":      rec["Date"],
#         "statement": rec["Statement"],
#         "category":  rec.get("Category", "Other"),
#         "entities":  entities,
#         "years":     years,
#         "relations": relations,
#     }

# ###############################################################################
# # 5️⃣ Cypher templates                                                        #
# ###############################################################################
# # --- stage-1: Case / Source / Event / Entity / Year ---------------------------
# _CORE_CYPHER = """
# MERGE (c:Case {name:$case})
# MERGE (f:Source {case:$case, name:$source})
#   ON CREATE SET f.ingestedAt=datetime($ingestedAt)
# MERGE (c)-[:HAS_FILE]->(f)
# WITH f, $rows AS rows                                   // <-- WITH required
# UNWIND rows AS row
# MERGE (ev:Event {id:row.evId})
#   ON CREATE SET ev.date      = date(row.date),
#                 ev.statement = row.statement,
#                 ev.category  = row.category
# MERGE (f)-[:HAS_EVENT]->(ev)
# WITH ev, row                                             // keep variables
# UNWIND row.entities AS eName
# MERGE (e:Entity {case:$case, name:eName})
# MERGE (ev)-[:INVOLVES]->(e)
# WITH ev, row
# UNWIND row.years AS yy
# MERGE (y:Year {value:yy})
# MERGE (ev)-[:HAPPENED_IN]->(y);
# """

# # --- stage-2: generic S-P-O → :REL edges ------------------------------------
# _REL_CYPHER = """
# UNWIND $triples AS t
# MATCH (sub:Entity {case:$case, name:t.subj})
# FOREACH (_ IN CASE WHEN t.objIsYear THEN [1] ELSE [] END |
#   MERGE (y:Year {value:toInteger(t.obj)})
#   MERGE (sub)-[:REL {relType:t.pred, eventId:t.evId}]->(y)
# )
# FOREACH (_ IN CASE WHEN t.objIsYear THEN [] ELSE [1] END |
#   MERGE (obj:Entity {case:$case, name:t.obj})
#   MERGE (sub)-[:REL {relType:t.pred, eventId:t.evId}]->(obj)
# );
# """

# ###############################################################################
# # 6️⃣ Ingest function                                                         #
# ###############################################################################

# def push_to_neo4j(case_name: str, file_name: str, rows: List[Dict[str, Any]]) -> ResultSummary:
#     """Ingest one PDF/link worth of rows from the LLM prompt."""
#     prepared = [_prep_row(case_name, r) for r in rows]

#     with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as drv, drv.session() as s:
#         # stage-1: core graph
#         core = s.run(
#             _CORE_CYPHER,
#             case=case_name,
#             source=file_name,
#             ingestedAt=datetime.now(timezone.utc).isoformat(),
#             rows=prepared,
#         ).consume()

#         # stage-2: per-row relations
#         for r in prepared:
#             triple_params = []
#             for rel_obj in r["relations"]:
#                 subj = rel_obj.get("Subject", "").strip()
#                 pred = rel_obj.get("Predicate", "").strip()
#                 obj  = rel_obj.get("Object", "").strip()
#                 if not subj or not pred or not obj:
#                     continue
#                 triple_params.append({
#                     "subj": subj,
#                     "pred": pred,
#                     "obj":  obj,
#                     "objIsYear": bool(re.fullmatch(r"\d{4}", obj)),
#                     "evId": r["evId"],
#                 })
#             if triple_params:
#                 s.run(_REL_CYPHER, case=case_name, triples=triple_params).consume()

#     print(f"📥 {file_name}@{case_name}: +{core.counters.nodes_created} nodes, +{core.counters.relationships_created} rels")
#     return core


# _YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

# def _extract_years(text: str) -> List[int]:
#     return [int(m.group()) for m in _YEAR_RE.finditer(text)]

# def _hash_event(case_name: str, date: str, stmt: str) -> str:
#     return hashlib.sha256(f"{case_name}|{date}|{stmt}".encode()).hexdigest()

# # --- Row preparation ---
# def _prep_row(case_name: str, rec: Dict[str, Any]) -> Dict[str, Any]:
#     years = _extract_years(rec["Statement"])
#     entities = [e.strip() for e in rec["Entities"].split(";") if e.strip()]
#     entity_types = rec.get("EntityTypes", [])
#     entity_info = []
#     for i, e in enumerate(entities):
#         entity_info.append({
#             "name": e,
#             "type": entity_types[i] if i < len(entity_types) else "other"
#         })
#     relations = rec.get("Relations", [])
#     return {
#         "evId": _hash_event(case_name, rec["Date"], rec["Statement"]),
#         "date": rec["Date"],
#         "statement": rec["Statement"],
#         "category": rec.get("Category", "Other"),
#         "entities": entity_info,
#         "years": years,
#         "relations": relations,
#     }

# # --- Cypher templates ---
# _CORE_CYPHER = """
# MERGE (c:Case {name:$case})
# MERGE (f:Source {case:$case, name:$source})
#   ON CREATE SET f.ingestedAt=datetime($ingestedAt)
# MERGE (c)-[:HAS_FILE]->(f)
# WITH f, $rows AS rows
# UNWIND rows AS row
# MERGE (ev:Event {id:row.evId})
#   ON CREATE SET ev.date      = date(row.date),
#                 ev.statement = row.statement,
#                 ev.category  = row.category
# MERGE (f)-[:HAS_EVENT]->(ev)
# WITH ev, row
# UNWIND row.entities AS e
# MERGE (ent:Entity {case:$case, name:e.name})
#   ON CREATE SET ent.type = e.type
# MERGE (ev)-[:INVOLVES]->(ent)
# WITH ev, row
# UNWIND row.years AS yy
# MERGE (y:Year {value:yy})
# MERGE (ev)-[:HAPPENED_IN]->(y);
# """

# _REL_CYPHER = """
# UNWIND $triples AS t
# MATCH (sub:Entity {case:$case, name:t.subj})
# FOREACH (_ IN CASE WHEN t.objIsYear THEN [1] ELSE [] END |
#   MERGE (y:Year {value:toInteger(t.obj)})
#   MERGE (sub)-[:REL {relType:t.pred, eventId:t.evId}]->(y)
# )
# FOREACH (_ IN CASE WHEN t.objIsYear THEN [] ELSE [1] END |
#   MERGE (obj:Entity {case:$case, name:t.obj})
#   MERGE (sub)-[:REL {relType:t.pred, eventId:t.evId}]->(obj)
# );
# """

# # --- Final ingest function ---
# def push_to_neo4j(case_name: str, file_name: str, rows: List[Dict[str, Any]]) -> ResultSummary:
#     prepared = [_prep_row(case_name, r) for r in rows]

#     with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as drv, drv.session() as s:
#         core = s.run(
#             _CORE_CYPHER,
#             case=case_name,
#             source=file_name,
#             ingestedAt=datetime.now(timezone.utc).isoformat(),
#             rows=prepared,
#         ).consume()

#         for r in prepared:
#             triple_params = []
#             for rel_obj in r["relations"]:
#                 subj = rel_obj.get("Subject", "").strip()
#                 pred = rel_obj.get("Predicate", "").strip()
#                 obj  = rel_obj.get("Object", "").strip()
#                 if not subj or not pred or not obj:
#                     continue
#                 triple_params.append({
#                     "subj": subj,
#                     "pred": pred,
#                     "obj": obj,
#                     "objIsYear": bool(re.fullmatch(r"\d{4}", obj)),
#                     "evId": r["evId"],
#                 })
#             if triple_params:
#                 s.run(_REL_CYPHER, case=case_name, triples=triple_params).consume()

#     print(f"📥 {file_name}@{case_name}: +{core.counters.nodes_created} nodes, +{core.counters.relationships_created} rels")
#     return core


# Push dat ainto neo4j with embedding

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

# _CORE_CYPHER = """
# MERGE (c:Case {name:$case})
# MERGE (f:Source {case:$case, name:$source})
#   ON CREATE SET f.ingestedAt=datetime($ingestedAt)
# MERGE (c)-[:HAS_FILE]->(f)
# WITH f, $case AS case_name, $rows AS rows
# UNWIND rows AS row
# MERGE (ev:Event {id:row.evId})
#   ON CREATE SET ev.date      = date(row.date),
#                 ev.statement = row.statement,
#                 ev.category  = row.category,
#                 ev.embedding = row.embedding,
#                 ev.case      = case_name
# MERGE (f)-[:HAS_EVENT]->(ev)
# WITH ev, row
# UNWIND row.entities AS e
# MERGE (ent:Entity {case:$case, name:e.name})
#   ON CREATE SET ent.type = e.type
# MERGE (ev)-[:INVOLVES]->(ent)
# WITH ev, row
# UNWIND row.years AS yy
# MERGE (y:Year {value:yy})
# MERGE (ev)-[:HAPPENED_IN]->(y);
# """

# _REL_CYPHER = """
# UNWIND $triples AS t
# MATCH (sub:Entity {case:$case, name:t.subj})
# FOREACH (_ IN CASE WHEN t.objIsYear THEN [1] ELSE [] END |
#   MERGE (y:Year {value:toInteger(t.obj)})
#   MERGE (sub)-[:REL {relType:t.pred, eventId:t.evId}]->(y)
# )
# FOREACH (_ IN CASE WHEN t.objIsYear THEN [] ELSE [1] END |
#   MERGE (obj:Entity {case:$case, name:t.obj})
#   MERGE (sub)-[:REL {relType:t.pred, eventId:t.evId}]->(obj)
# );
# """

# class AsyncNeo4jIngestor:
#     def __init__(self, uri: str, user: str, password: str, llm_client: AsyncOpenAI):
#         self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
#         self.llm_client = llm_client

#     def _hash_event(self, case_name: str, date: str, stmt: str) -> str:
#         return hashlib.sha256(f"{case_name}|{date}|{stmt}".encode()).hexdigest()

#     async def _extract_years(self, text: str) -> List[int]:
#         return [int(m.group()) for m in _YEAR_RE.finditer(text)]

#     async def _generate_embedding(self, text: str) -> List[float]:
#         response = await self.llm_client.embeddings.create(
#             model="text-embedding-3-small",
#             input=text
#         )
#         return response.data[0].embedding

#     async def _prep_row(self, case_name: str, rec: Dict[str, Any]) -> Dict[str, Any]:
#         years = await self._extract_years(rec["Statement"])
#         entities = [e.strip() for e in rec["Entities"].split(";") if e.strip()]
#         entity_types = rec.get("EntityTypes", [])
#         entity_info = [
#             {"name": e, "type": entity_types[i] if i < len(entity_types) else "other"}
#             for i, e in enumerate(entities)
#         ]
#         embedding = await self._generate_embedding(rec["Statement"])
#         return {
#             "evId": self._hash_event(case_name, rec["Date"], rec["Statement"]),
#             "date": rec["Date"],
#             "statement": rec["Statement"],
#             "category": rec.get("Category", "Other"),
#             "entities": entity_info,
#             "years": years,
#             "relations": rec.get("Relations", []),
#             "embedding": embedding
#         }

#     async def push_to_neo4j(self, case_name: str, file_name: str, rows: List[Dict[str, Any]]) -> None:
#         prepared = [await self._prep_row(case_name, r) for r in rows]

#         async with self.driver.session() as session:
#             await session.run(
#                 _CORE_CYPHER,
#                 case=case_name,
#                 source=file_name,
#                 ingestedAt=datetime.now(timezone.utc).isoformat(),
#                 rows=prepared
#             )

#             for r in prepared:
#                 triple_params = []
#                 for rel_obj in r["relations"]:
#                     subj = rel_obj.get("Subject", "").strip()
#                     pred = rel_obj.get("Predicate", "").strip()
#                     obj  = rel_obj.get("Object", "").strip()
#                     if not subj or not pred or not obj:
#                         continue
#                     triple_params.append({
#                         "subj": subj,
#                         "pred": pred,
#                         "obj": obj,
#                         "objIsYear": bool(re.fullmatch(r"\d{4}", obj)),
#                         "evId": r["evId"]
#                     })
#                 if triple_params:
#                     await session.run(_REL_CYPHER, case=case_name, triples=triple_params)

#         print(f"📥 {file_name}@{case_name}: Inserted {len(prepared)} rows.")

llm_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class AsyncNeo4jEmbedIngestor:
    def __init__(self):
        self.driver = AsyncGraphDatabase.driver(URI, auth=(USER, PASSWORD))

    def _extract_years(self, text: str) -> List[int]:
        return [int(m.group()) for m in _YEAR_RE.finditer(text)]

    def _hash_event(self, case_name: str, date: str, stmt: str) -> str:
        return hashlib.sha256(f"{case_name}|{date}|{stmt}".encode()).hexdigest()

    async def _batch_generate_embeddings(self, statements: List[str]) -> List[List[float]]:
        response = await llm_client.embeddings.create(
            model="text-embedding-3-small",
            input=statements
        )
        return [item.embedding for item in response.data]

    async def _prepare_rows(self, case_name: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        statements = [r["Statement"] for r in rows]
        embeddings = await self._batch_generate_embeddings(statements)

        prepped = []
        for i, rec in enumerate(rows):
            years = self._extract_years(rec["Statement"])
            entities = [e.strip() for e in rec["Entities"].split(";") if e.strip()]
            entity_types = rec.get("EntityTypes", [])
            entity_info = [
                {"name": e, "type": entity_types[j] if j < len(entity_types) else "other"}
                for j, e in enumerate(entities)
            ]
            prepped.append({
                "evId": self._hash_event(case_name, rec["Date"], rec["Statement"]),
                "date": rec["Date"],
                "statement": rec["Statement"],
                "category": rec.get("Category", "Other"),
                "entities": entity_info,
                "years": years,
                "relations": rec.get("Relations", []),
                "embedding": embeddings[i]
            })
        return prepped

    async def push(self, case_name: str, file_name: str, doc_title: str, rows: List[Dict[str, Any]]) -> ResultSummary:
        prepared = await self._prepare_rows(case_name, rows)

        _CORE_CYPHER = """
        MERGE (c:Case {name:$case})
        MERGE (f:Source {case:$case, name:$source})
          ON CREATE SET f.ingestedAt=datetime($ingestedAt),
            f.docTitle = $doc_title
        MERGE (c)-[:HAS_FILE]->(f)
        WITH f, $case AS case_name, $rows AS rows
        UNWIND rows AS row
        MERGE (ev:Event {id:row.evId})
          ON CREATE SET ev.date = date(row.date),
                        ev.statement = row.statement,
                        ev.category = row.category,
                        ev.embedding = row.embedding,
                        ev.case = case_name
        MERGE (f)-[:HAS_EVENT]->(ev)
        WITH ev, row
        UNWIND row.entities AS e
        MERGE (ent:Entity {case:$case, name:e.name})
          ON CREATE SET ent.type = e.type
        MERGE (ev)-[:INVOLVES]->(ent)
        WITH ev, row
        UNWIND row.years AS yy
        MERGE (y:Year {value:yy})
        MERGE (ev)-[:HAPPENED_IN]->(y);
        """

        _REL_CYPHER = """
        UNWIND $triples AS t
        MATCH (sub:Entity {case:$case, name:t.subj})
        FOREACH (_ IN CASE WHEN t.objIsYear THEN [1] ELSE [] END |
          MERGE (y:Year {value:toInteger(t.obj)})
          MERGE (sub)-[:REL {relType:t.pred, eventId:t.evId}]->(y)
        )
        FOREACH (_ IN CASE WHEN t.objIsYear THEN [] ELSE [1] END |
          MERGE (obj:Entity {case:$case, name:t.obj})
          MERGE (sub)-[:REL {relType:t.pred, eventId:t.evId}]->(obj)
        );
        """

        async with self.driver.session() as s:
            core = await s.run(
                _CORE_CYPHER,
                case=case_name,
                source=file_name,
                doc_title=doc_title,
                ingestedAt=datetime.now(timezone.utc).isoformat(),
                rows=prepared
            )
            await core.consume()

            for r in prepared:
                triples = []
                for rel in r["relations"]:
                    subj = rel.get("Subject", "").strip()
                    pred = rel.get("Predicate", "").strip()
                    obj = rel.get("Object", "").strip()
                    if not subj or not pred or not obj:
                        continue
                    triples.append({
                        "subj": subj,
                        "pred": pred,
                        "obj": obj,
                        "objIsYear": bool(re.fullmatch(r"\d{4}", obj)),
                        "evId": r["evId"]
                    })
                if triples:
                    await s.run(_REL_CYPHER, case=case_name, triples=triples)

        print(f"📥 {file_name}@{case_name}: embedding + neo4j ingestion complete, {len(prepared)}")
        return core


neo4j_data_ingestor = AsyncNeo4jEmbedIngestor()
