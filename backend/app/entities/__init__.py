"""Event Intelligence Layer — the Knowledge Graph foundation.

A deterministic, storage-independent projection of the event catalog into canonical
entities (organizations, communities, companies, speakers, venues, cities, event series)
and their relationships. Reads the frozen Repository; builds a rebuildable graph; powers
entity queries and ecosystem analytics. No graph database, no LLM.
"""

from app.entities.analytics import entity_report
from app.entities.builder import GraphBuilder
from app.entities.graph import GraphStore, InMemoryGraphStore
from app.entities.models import Edge, EdgeType, Entity, EntityType
from app.entities.queries import EntityQueries
from app.entities.resolution import EntityResolver, normalize_name

__all__ = [
    "GraphBuilder",
    "GraphStore",
    "InMemoryGraphStore",
    "Entity",
    "Edge",
    "EntityType",
    "EdgeType",
    "EntityResolver",
    "normalize_name",
    "EntityQueries",
    "entity_report",
]
