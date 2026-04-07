---
name: knowledge-graph-querying
description: Query the Ninko Knowledge Graph for entity relationships, find paths between systems, discover related incidents, and analyze infrastructure dependencies.
modules: []
---

# Knowledge Graph Querying Skill

## Purpose

The Knowledge Graph stores structured entities and relationships from IT operations.
Use it to:
- Find dependencies between systems
- Discover related incidents and their root causes
- Analyze infrastructure topology
- Suggest related entities based on graph proximity

## Entity Types

- **module**: IT modules (proxmox, kubernetes, pihole, etc.)
- **service**: Services running on systems
- **host**: Physical or virtual machines
- **configuration**: Settings and configs
- **incident**: Recorded incidents with details
- **user**: Users in the system
- **tag**: Labels and categorizations
- **runbook**: Operational procedures
- **workflow**: Automation workflows
- **agent**: AI agents in the system

## Relationship Types

- `depends_on`: System A depends on System B
- `triggers`: Event A triggers Event B
- `resolved_by`: Incident was resolved by Entity
- `similar_to`: Entities are similar
- `configured_with`: Entity uses Configuration
- `manages`: Entity manages another Entity
- `part_of`: Entity is part of another Entity
- `caused_by`: Incident was caused by Entity
- `has_tag`: Entity has Tag
- `executed_by`: Workflow/Runbook executed by Entity

## Query Patterns

### Find Dependencies
```
GET /api/knowledge-graph/entities/{id}/neighbors?relation_type=depends_on
```

### Find Path Between Systems
```
GET /api/knowledge-graph/path?source={A}&target={B}&max_depth=5
```

### Get Related Suggestions
```
GET /api/knowledge-graph/entities/{id}/suggestions
```

### Find Communities (Clusters)
```
GET /api/knowledge-graph/communities
```

### Get Most Central Entities
```
GET /api/knowledge-graph/centrality?top_k=10
```

## Usage Examples

1. **Before troubleshooting**: Check what depends on a failing service
2. **After incident**: Extract entities from incident for future reference
3. **Analysis**: Find communities of related systems
4. **Planning**: Discover path/dependencies before making changes

## Integration with RAG

The Knowledge Graph works alongside ChromaDB Semantic Memory:
- ChromaDB: Semantic similarity search
- Knowledge Graph: Structured relationship queries
- Together: Powerful hybrid RAG for complex IT questions
