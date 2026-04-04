# Qdrant Module

Semantic knowledge storage and retrieval with Qdrant.

## Features
- Semantic search in knowledge collections
- Add and delete knowledge entries
- List collections and collection stats

## Connection
Configure in **Settings -> Modules -> Qdrant**.

Typical fields:
- `url` (e.g. `http://qdrant:6333`)
- optional API key

## Main Tools
- `search_knowledge`
- `add_knowledge`
- `delete_knowledge_by_id`
- `list_knowledge_collections`
- `get_collection_stats`

## Notes
- Keep embeddings/model configuration consistent across all inserted documents.
- Use tags/categories to improve retrieval precision.
