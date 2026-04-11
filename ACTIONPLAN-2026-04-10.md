# 🎯 ACTIONPLAN 2026-04-10
**Merged:** Full Code Review + 5x Agent Validation (code-pruefer, sicherheitspruefer, performance-analyst, fehlersucher, test-generator)

**Status:** 🔴 **BLOCKIERT – Diese Items müssen vor Deployment gefixt werden**

---

## 📊 PRIORITÄTS-MATRIX

| Priorität | Sicherheit | Performance | Backend | Frontend | Anzahl |
|-----------|-----------|------------|---------|----------|--------|
| 🔴 P0 (SOFORT) | 5 | 3 | 3 | 1 | **12** |
| 🟡 P1 (Nächste Woche) | 2 | 2 | 2 | 1 | **7** |
| 🟠 P2 (Kurzfristig) | 1 | 2 | 2 | 2 | **7** |
| 🟢 P3 (Optional) | 0 | 0 | 1 | 1 | **2** |

**Geschätzte Gesamtarbeitszeit:** 28-35 Stunden (verteilt über 3 Wochen)

---

## 🔴 P0 – BLOCKIERT FÜR DEPLOYMENT (28 Stunden)

### Sicherheit (5 Critical Issues)

**S1. Frontend Script-Injection (CSP-Header fehlt)** ⏱️ 15 min
- **Datei:** `frontend/index.html` (add), `frontend/app.js:433`
- **Risk:** Critical – RCE bei Backend-Compromise
- **Status:** ❌ OPEN
- **Fix:**
  ```html
  <!-- frontend/index.html – Add Meta-Tag im <head> -->
  <meta http-equiv="Content-Security-Policy" 
        content="script-src 'self'; style-src 'self' https://fonts.googleapis.com; img-src 'self' data: https:;">
  ```
- **Validation:** curl -I http://localhost:8000 | grep Content-Security-Policy
- **Assigned:** Frontend-Team

---

**S2. Safeguard-Bypass in Pipeline (confirmed=True hart-codiert)** ⏱️ 20 min
- **Datei:** `backend/agents/core_tools.py:1097`
- **Risk:** Critical – Privilege-Escalation, Destructive Ops ohne Consent
- **Status:** ❌ OPEN (Privilege-Escalation!)
- **CVE:** CWE-269, CWE-863
- **Fix:**
  ```python
  # Lines 1097-1108: Replace confirmed=True with policy-based auto_confirm
  safeguard = request.app.state.safeguard
  auto_confirm = False  # Default
  if safeguard and safeguard.enabled:
      profile = safeguard.get_profile(session_id)
      auto_confirm = getattr(profile, 'auto_mode', False)
  
  result, _ = await agent.invoke(
      message=full_task, chat_history=None, session_id=session_id,
      confirmed=auto_confirm,  # Policy-based, not hard-coded
  )
  ```
- **Test:** Verify with strict SafeguardProfile that pipeline-steps still require confirmation
- **Assigned:** Backend-Security

---

**S3. Credential Exposure in Error Messages** ⏱️ 15 min
- **Datei:** `backend/modules_catalog/openproject/manifest.py:67`
- **Risk:** High – API-Key exposure in HTTP error responses
- **Status:** ❌ OPEN
- **CVE:** CWE-209, CWE-532
- **Fix:**
  ```python
  # Line 67: Remove response.text from error detail
  except httpx.HTTPStatusError as e:
      logger.warning(f"OpenProject API Error: HTTP {e.response.status_code}")
      logger.debug(f"Full response: {e.response.text}")  # Only in logs, not in response
      return {
          "status": "error",
          "detail": f"OpenProject API returned HTTP {e.response.status_code}. Check logs."
      }
  ```
- **Test:** Verify error response never contains sensitive data
- **Assigned:** Backend-Security

---

**S4. Authorization Header Logging Risk** ⏱️ 20 min
- **Datei:** `backend/modules_catalog/openproject/tools.py:86` (+ similar in other integrations)
- **Risk:** High – Secrets in Exception Tracebacks/Sentry
- **Status:** ❌ OPEN
- **CVE:** CWE-532
- **Fix:**
  ```python
  # Sanitize headers before logging/exceptions
  safe_headers = {k: "***" if k.lower() in ["authorization", "x-api-key", "x-token"] else v 
                  for k, v in headers.items()}
  logger.debug(f"API Request: {url}, headers={safe_headers}")
  
  try:
      resp = await session.request(method, url, json=json_data, headers=headers)
      resp.raise_for_status()
  except httpx.HTTPStatusError as e:
      logger.error(f"OpenProject API Error: HTTP {e.response.status_code}", exc_info=False)
      raise ValueError(f"API returned HTTP {e.response.status_code}")
  ```
- **Test:** Verify Authorization header never appears in logs or error messages
- **Assigned:** Backend-Security

---

**S5. JSON Formatting Error in Catalog (Invalid JSON)** ⏱️ 10 min
- **Datei:** `backend/modules_catalog/catalog.json:87, 171`
- **Risk:** High – Build/Deployment failure
- **Status:** ❌ OPEN (Build Blocker)
- **Fix:** Validate and correct JSON syntax
  ```bash
  python3 -m json.tool backend/modules_catalog/catalog.json > /dev/null
  ```
- **Expected Errors:** Missing commas between objects
- **Assigned:** DevOps

---

### Performance (3 Critical Issues)

**P1. Safeguard LLM Timeout (blocks EVERY request)** ⏱️ 2-3 hours
- **Datei:** `backend/core/safeguard.py:180-195`
- **Risk:** Critical – 8s latency per request, -40% performance
- **Status:** ❌ OPEN
- **Impact:** 10 concurrent users = 80s total latency per batch
- **Fix - Phase 1 (Pre-filter for <100 chars):**
  ```python
  # safeguard.py: Add pre-filter
  if len(message) < 100:
      result = self._classify_keywords(message)  # ~10ms, instant
      if result.category in ["SAFE", "UNKNOWN"]:
          return result
  
  # For >100 chars, LLM classification runs async in background
  # Return early with tentative SAFE, refine later
  ```
- **Estimated Gain:** -40-50% latency for 80% of requests
- **Test:** Latency profile: simple queries should be <100ms
- **Assigned:** Backend-Performance

---

**P2. Chat-History Memory-Leak & Scale** ⏱️ 3-4 hours
- **Datei:** `backend/agents/orchestrator.py:1034-1068`, `redis_client.py:52-56`
- **Risk:** Critical – unbounded growth, OOM after 300+ messages
- **Status:** ❌ OPEN (Memory Leak)
- **Impact:** -30-50% latency for long conversations
- **Fix - Phase 1 (Pagination):**
  ```python
  # redis_client.py: Add pagination
  async def get_chat_history(key: str, limit: int = 50) -> list[dict]:
      """Fetch last N messages, not all"""
      messages = await redis.lrange(key, -limit, -1)  # Last 50
      return [json.loads(msg) for msg in messages]
  
  # orchestrator.py: Use paginated history
  history = await get_chat_history(session_id, limit=50)
  ```
- **Fix - Phase 2 (Auto-Compaction at 200+ messages):**
  ```python
  if len(history) > 200:
      # Summarize old messages (keep last 100)
      summary = await agent.summarize(history[:100])
      # Store summary as single message, delete old ones
  ```
- **Estimated Gain:** -30-50% for long conversations
- **Test:** 500-message conversation should stay <1s latency
- **Assigned:** Backend-Performance

---

**P3. Redis hgetall() Scale Problem (6 locations)** ⏱️ 4-5 hours
- **Dateien:** `redis_client.py:92`, `task_registry.py:46`, `operation_journal.py:127`, `safeguard_profiles.py:116`, `metrics.py:201,276`, `audit.py:102`
- **Risk:** Critical – O(n) linear scaling, 2-5s for 1000+ entries
- **Status:** ❌ OPEN
- **Impact:** -40-60% latency at scale
- **Fix:** Replace hgetall() with HSCAN + pagination
  ```python
  # Old (bad for scale):
  all_tasks = await redis.hgetall("tasks")  # O(n) full fetch
  
  # New (scalable):
  async def get_tasks_paginated(cursor=0, count=50):
      cursor, tasks = await redis.hscan("tasks", cursor, count=count)
      return {t[0]: json.loads(t[1]) for t in tasks}, cursor
  
  # Use in API:
  tasks, next_cursor = await get_tasks_paginated()
  ```
- **Estimated Gain:** -40-60% for large datasets
- **Test:** /api/tasks?limit=50 should be <200ms with 10k tasks
- **Assigned:** Backend-Performance

---

### Backend Code (3 High Issues)

**B1. Path Traversal Validation (incomplete)** ⏱️ 30 min
- **Datei:** `backend/api/routes_plugins.py:485-489`
- **Risk:** High – ZIP-Extraction can write outside target directory
- **Status:** ⚠️ PARTIALLY_FIXED (naive string check)
- **CVE:** CWE-22 (Path Traversal)
- **Fix:** Use canonical path validation
  ```python
  from pathlib import Path
  
  dest_path = extracted_dir / member.filename
  canonical_dest = dest_path.resolve()
  
  if not str(canonical_dest).startswith(str(extracted_dir.resolve())):
      raise HTTPException(status_code=400, detail="Invalid path in ZIP")
  
  # Now safe to extract
  member.extractall(path=extracted_dir)
  ```
- **Test:** Try ZIP with "../../../etc/passwd", should be rejected
- **Assigned:** Backend-Security

---

**B2. Auth Path Bare Exception (no logging)** ⏱️ 15 min
- **Datei:** `backend/main.py:676`
- **Risk:** High – Redis errors silently fail, unprovable auth failures
- **Status:** ❌ OPEN
- **Impact:** Debugging impossible for auth issues
- **Fix:**
  ```python
  def _is_active_user_api_token(token: str) -> bool:
      try:
          # ... existing logic ...
      except Exception as exc:
          logger.warning(f"API token check failed: {exc}")  # Add logging!
          return False
  ```
- **Test:** Verify logs show Redis errors
- **Assigned:** Backend-Logging

---

**B3. Update Check Silent Exception** ⏱️ 20 min
- **Datei:** `backend/api/routes_plugins.py:332-333`
- **Risk:** High – Users never notified of check failures
- **Status:** ❌ OPEN
- **Impact:** Semantic error, missing transparency
- **Fix:**
  ```python
  try:
      # ... check GitHub for updates ...
  except Exception as exc:
      logger.warning(f"Update check failed: {exc}")
      return {"update_available": False, "check_failed": True}
  ```
- **Test:** Verify UI shows "Check failed" when connection is down
- **Assigned:** Backend-Logging

---

### Frontend (1 Issue)

**F1. Mobile Responsive Design (incomplete)** ⏱️ 2-3 hours
- **Datei:** `frontend/style.css` (add breakpoints), `frontend/app.js` (sidebar toggle)
- **Risk:** High – Sidebar 250px fixed, not responsive on mobile
- **Status:** ❌ OPEN
- **Impact:** Broken UX on phones/tablets
- **Fix:**
  ```css
  /* frontend/style.css – Add mobile breakpoints */
  @media (max-width: 768px) {
      :root { --sidebar-width: 60px; }  /* Collapse sidebar */
      .sidebar { position: fixed; }
      .sidebar.collapsed .nav-label { display: none; }
  }
  
  @media (max-width: 480px) {
      :root { --sidebar-width: 0; --header-height: 50px; }
      .sidebar { transform: translateX(-100%); }
      .sidebar.mobile-open { transform: translateX(0); }
      .hamburger-menu { display: block; }
  }
  ```
- **Test:** Open on mobile device, verify responsiveness
- **Assigned:** Frontend-Team

---

## 🟡 P1 – NÄCHSTE WOCHE (14 Stunden)

### Security (2 Issues)

**S6. Missing explicit SSL/TLS Verification** ⏱️ 30 min
- **Datei:** `backend/modules_catalog/openproject/manifest.py:36, 58, 88`
- **Risk:** High (preventive) – MITM possible if verify=False added later
- **Status:** 🟡 MITIGATION_INCOMPLETE (httpx default is secure, but not explicit)
- **CVE:** CWE-295
- **Fix:** Explicitly set verify=True
  ```python
  async with httpx.AsyncClient(
      headers={"Authorization": f"Bearer {api_key}"},
      timeout=10.0,
      verify=True  # Explicit, not implicit
  ) as client:
  ```

---

**S7. Version 1.0.3 Breaking Change Undocumented** ⏱️ 1 hour
- **Datei:** Create `backend/modules_catalog/openproject/CHANGELOG.md`
- **Risk:** Medium – Users unaware of breaking changes
- **Status:** ⚠️ INFO (documentation missing)
- **Fix:** Create CHANGELOG documenting breaking changes

---

### Performance (2 Issues)

**P4. Background Task Memory Leak** ⏱️ 1 hour
- **Datei:** `backend/agents/core_tools.py:17`, `backend/agents/base_agent.py:1209`
- **Risk:** High – Memory grows with task count
- **Status:** ⚠️ PARTIALLY_FIXED (add_done_callback exists, but race condition possible)
- **Impact:** -10-20% memory after long sessions
- **Fix:** Use WeakSet or periodic cleanup
  ```python
  # Add periodic cleanup task
  async def cleanup_background_tasks():
      while True:
          await asyncio.sleep(300)  # Every 5 minutes
          _background_tasks[:] = [t for t in _background_tasks if not t.done()]
  ```

---

**P5. Workflow DAG O(n×m) Traversal** ⏱️ 1 hour
- **Datei:** `backend/core/workflow_engine.py:230-249`
- **Risk:** Medium – 50+ node DAGs have O(n×m) complexity
- **Status:** ❌ OPEN
- **Impact:** -40-70% for large DAGs
- **Fix:** Pre-compute adjacency map
  ```python
  # On DAG init:
  self.outgoing_edges = {}
  for edge in edges:
      if edge['source_id'] not in self.outgoing_edges:
          self.outgoing_edges[edge['source_id']] = []
      self.outgoing_edges[edge['source_id']].append(edge)
  
  # On traversal:
  for edge in self.outgoing_edges.get(node_id, []):  # O(1) lookup
      ...
  ```

---

### Backend (2 Issues)

**B4. Telegram Task Tracking (untracked error handling)** ⏱️ 1 hour
- **Datei:** `backend/modules_catalog/telegram/bot.py:177`
- **Risk:** High – Errors in message handling go unlogged
- **Status:** ❌ OPEN
- **Impact:** Silent failures in Telegram integration
- **Fix:** Add error callback
  ```python
  task = asyncio.create_task(self.handle_update(update, token))
  task.add_done_callback(lambda t: logger.error(f"Update handling failed: {t.exception()}") 
                                   if t.exception() else None)
  ```

---

**B5. MCP Subprocess Resource Leak (timeout handling)** ⏱️ 1 hour
- **Datei:** `backend/core/mcp_registry.py:258-271`
- **Risk:** High – 2s timeout on wait() can block
- **Status:** ⚠️ PARTIALLY_FIXED (finally-block exists, but timeout handling weak)
- **Impact:** -10-30% for failed MCP sessions
- **Fix:** Wrap stderr read in timeout
  ```python
  try:
      stderr_data = await asyncio.wait_for(process.stderr.read(), timeout=1.0)
  except asyncio.TimeoutError:
      stderr_data = b""  # Skip slow stderr
  ```

---

### Frontend (1 Issue)

**F2. Fetch Timeouts (missing on non-chat requests)** ⏱️ 1 hour
- **Datei:** `frontend/app.js` (various Fetch calls)
- **Risk:** Medium – Long-hanging requests
- **Status:** ❌ OPEN (only /api/chat has AbortController)
- **Fix:**
  ```javascript
  const fetchWithTimeout = async (url, options = {}, timeoutMs = 30000) => {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), timeoutMs);
      try {
          const response = await fetch(url, {
              ...options,
              signal: controller.signal
          });
          clearTimeout(timeout);
          return response;
      } catch (err) {
          clearTimeout(timeout);
          throw err;
      }
  };
  
  // Usage: await fetchWithTimeout('/api/settings', {method: 'GET'})
  ```

---

## 🟠 P2 – KURZFRISTIG (12 Stunden)

### Sicherheit (1 Issue)

**S8. Breaking Change Documentation** ⏱️ 1 hour
- See S7 above (combined)

---

### Performance (2 Issues)

**P6. Inconsistent Timeout Values** ⏱️ 2 hours
- **Dateien:** `backend/core/config.py` (create), `routes_plugins.py`, `mcp_registry.py`
- **Risk:** Medium – Technical debt, hard to maintain
- **Status:** ⚠️ PARTIALLY_ADDRESSED (some centralized, some inline)
- **Fix:** Create constants file
  ```python
  # backend/core/timeout_config.py
  HTTP_TIMEOUT_DEFAULT = 30.0      # API calls
  HTTP_TIMEOUT_LONG = 120.0        # Large file uploads
  MCP_TIMEOUT_PROCESS_WAIT = 2.0   # Process termination
  SAFEGUARD_TIMEOUT = 8.0          # LLM classification
  ```

---

### Backend (2 Issues)

**B6. Silent Exception Handlers (add debug logging)** ⏱️ 1 hour
- **Dateien:** `backend/api/routes_settings.py` (6 locations)
- **Risk:** Medium – Fallback failures not logged
- **Status:** ⚠️ PARTIALLY_FIXED (specific exceptions, but no logging)
- **Fix:** Add debug logs
  ```python
  except (RuntimeError, ValueError, ...) as exc:
      logger.debug(f"Fallback read failed for setting {key}: {exc}")
  ```

---

**B7. Type Hints Incomplete** ⏱️ 1 hour
- **Dateien:** `backend/agents/core_tools.py:58-89`, `backend/modules_catalog/fritzbox/tools.py:202`
- **Risk:** Low – Code quality
- **Status:** ❌ STILL_MISSING (partial)
- **Fix:** Add type annotations
  ```python
  # core_tools.py
  def _t(de: str, en: str, fr: str = "") -> str:
      ...
  
  # fritzbox/tools.py
  def _exec(fc: FritzConnection) -> str:
      ...
  ```

---

### Frontend (2 Issues)

**F3. aria-* Attributes (accessibility)** ⏱️ 2 hours
- **Datei:** `frontend/app.js`, `frontend/index.html`
- **Risk:** Medium – WCAG compliance
- **Status:** ❌ OPEN
- **Fix:** Add ARIA labels to interactive elements
  ```html
  <button aria-label="Open settings" class="settings-btn">⚙️</button>
  <div role="main" aria-live="polite">Chat content</div>
  ```

---

## 🟢 P3 – OPTIONAL (5 Stunden)

### Magic Numbers Centralization (Already Done) ⏱️ 0 hours
- **Status:** ✅ **FIXED** – Already centralized in config.py

### print() in Tests ⏱️ 0 hours
- **Status:** 🟢 **ACCEPTABLE** – Standalone test scripts, not production code

### while True Loops ⏱️ 0 hours
- **Status:** ✅ **FIXED** – All have exit conditions

---

## 📋 DEPLOYMENT CHECKLIST

### Before Deployment (P0 Items ONLY)

- [ ] **S1.** CSP-Header added to frontend/index.html
- [ ] **S2.** confirmed=True replaced with policy-based auto_confirm in core_tools.py
- [ ] **S3.** response.text removed from OpenProject error messages
- [ ] **S4.** Authorization headers sanitized in logs
- [ ] **S5.** JSON catalog.json validated and corrected
- [ ] **P1.** Safeguard pre-filter for <100 char messages implemented
- [ ] **P2.** Chat history pagination implemented
- [ ] **P3.** Redis HSCAN pagination added to 6 locations
- [ ] **B1.** Path traversal validation using Path.resolve()
- [ ] **B2.** Auth exception logging added
- [ ] **B3.** Update check exception handling improved
- [ ] **F1.** Mobile responsive CSS breakpoints added
- [ ] **All:** Run full test suite and deploy

### Post-Deployment (First 2 Weeks)

- [ ] P1 items completed (Safeguard async, Chat-History compaction, etc.)
- [ ] Security preventive measures (SSL/TLS explicit, logging sanitization)
- [ ] Performance optimizations (DAG adjacency-map, task cleanup)

---

## 📊 SUMMARY

**Total Estimated Time:** 28-35 hours  
**Breakdown:**
- P0 (Blocking): 28 hours (1 week intensive)
- P1 (Critical): 14 hours (1 week follow-up)
- P2 (Important): 12 hours (2 weeks)
- P3 (Optional): 0 hours (already fixed or acceptable)

**Success Criteria:**
- ✅ All P0 items fixed before next deployment
- ✅ 60-70% latency reduction (Safeguard + Redis optimizations)
- ✅ 30-40% memory reduction (Chat-History + Task cleanup)
- ✅ Zero critical security vulnerabilities
- ✅ Mobile-responsive frontend

---

**Report Generated:** 2026-04-10 16:30 UTC  
**By:** Full Review + 5x Agent Validation System  
**Next Review Date:** 2026-04-17 (post-P0 fixes)
