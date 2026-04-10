"""
ninko.app – Ninko application-specific code.

This package contains:
    - Orchestrator routing (orchestrator)
    - Module discovery (module_registry)
    - Dynamic agent pool (agent_pool)
    - Skills management (skills_manager)
    - Soul management (soul_manager)
    - SafeGuard middleware (safeguard)
    - Connection management (connections)
    - Workflow engine (workflow_engine)
    - Theme management (theme_manager)
    - Knowledge graph (knowledge_graph)
    - Module agents (modules, modules_catalog)
    - API routes (api)

RULE: app MAY import from ninko.harness.*
RULE: app MUST NOT be imported by ninko.harness.*
"""
