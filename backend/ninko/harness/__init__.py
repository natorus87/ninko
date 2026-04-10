"""
ninko.harness – Domain-agnostic agent framework.

This package contains the reusable core:
    - LLM abstraction (llm_factory)
    - Memory backends (memory)
    - Redis client (redis_client)
    - Secrets vault (vault)
    - Context management (context_manager)
    - Configuration (config)
    - Authentication & RBAC (auth, rbac)
    - Rate limiting (rate_limit)
    - TLS support (tls)
    - Base agent class (base_agent)
    - Middleware infrastructure (middleware)
    - Event system (events, status_bus)
    - Core schemas (schemas)

RULE: harness MUST NOT import from ninko.app.* or ninko.modules.*
"""
