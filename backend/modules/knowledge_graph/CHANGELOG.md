# Changelog

All notable changes to the Knowledge Graph module will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-04-07

### Added
- Initial release of Knowledge Graph module
- NetworkX-based directed graph for IT entities and relationships
- Entity types: module, service, host, configuration, incident, user, tag, runbook, workflow, agent
- Relationship types: depends_on, triggers, resolved_by, similar_to, configured_with, manages, part_of, caused_by, has_tag, executed_by
- Graph algorithms: PageRank centrality, Louvain communities, path finding
- Smart incident extraction (automatic entity/relationship creation)
- Hybrid RAG integration (ChromaDB semantic + Knowledge Graph structural)
- 20+ API endpoints for CRUD, queries, analytics
- 4 core tools for agents: kg_find_related, kg_find_path, kg_analyze_dependencies, kg_record_incident
- Frontend visualization with Cytoscape.js
- Export/Import in node-link JSON format
- Statistics and graph metrics

### Features
- **Graph Traversal**: Find paths between systems, discover dependencies
- **Impact Analysis**: Calculate affected systems for outage planning
- **Community Detection**: Identify clusters of related infrastructure
- **Semantic Bridge**: Link to ChromaDB for hybrid search
- **Auto-Learning**: Extract entities automatically from incidents
- **Visualization**: Interactive graph with filtering and zooming
