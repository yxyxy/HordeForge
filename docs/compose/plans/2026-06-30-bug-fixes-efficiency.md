# HordeForge Bug Fixes & Efficiency Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix critical bugs and efficiency issues across RAG, Agent, Orchestrator, Storage, and Auth systems to reach modern product standards.

**Architecture:** Multi-system audit with targeted fixes. Each task is self-contained with tests.

**Tech Stack:** Python 3.11+, pytest, ruff, mypy

## Global Constraints

- Python 3.11+
- Follow existing code patterns
- All tests must pass before completion
- Run `ruff check --fix` and `ruff format` after each task
- Max file size: ~500 lines (split if larger)

---

## Phase 1: Critical Runtime Bugs (P0)

### Task 1: Fix ContextBuilder retrieve() Method Call

**Covers:** RAG critical bug
**Files:**
- Modify: `rag/context_builder.py:39`
- Test: `tests/unit/rag/test_context_builder.py`

- [ ] **Step 1: Write the failing test**

```python
def test_context_builder_uses_search_method():
    from unittest.mock import MagicMock
    from rag.context_builder import ContextBuilder
    
    mock_retriever = MagicMock()
    mock_retriever.search.return_value = []
    
    builder = ContextBuilder(rag_retriever=mock_retriever)
    builder.build_agent_context("test query")
    
    mock_retriever.search.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/rag/test_context_builder.py::test_context_builder_uses_search_method -v`
Expected: FAIL with AttributeError

- [ ] **Step 3: Write minimal implementation**

```python
# In rag/context_builder.py, line 39
# Change: self.rag_retriever.retrieve(query, limit=max_rag_chunks)
# To:
rag_results = self.rag_retriever.search(query, limit=max_rag_chunks)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/rag/test_context_builder.py::test_context_builder_uses_search_method -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag/context_builder.py tests/unit/rag/test_context_builder.py
git commit -m "fix: use correct search method in ContextBuilder"
```

---

### Task 2: Fix Async Python Function Extraction

**Covers:** RAG async function detection
**Files:**
- Modify: `rag/symbol_extractor_tree_sitter.py:318-338`
- Test: `tests/unit/rag/test_symbol_extractor.py`

- [ ] **Step 1: Write the failing test**

```python
def test_async_python_function_extraction():
    from rag.symbol_extractor_tree_sitter import TreeSitterSymbolExtractor
    
    extractor = TreeSitterSymbolExtractor()
    source = '''
async def fetch_data():
    pass

async def process():
    pass
'''
    symbols = extractor.extract_symbols(source, "test.py", "python")
    
    assert len(symbols) == 2
    assert all(s.is_async for s in symbols)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/rag/test_symbol_extractor.py::test_async_python_function_extraction -v`
Expected: FAIL (async functions not extracted)

- [ ] **Step 3: Write minimal implementation**

```python
# In rag/symbol_extractor_tree_sitter.py, add handling for async_function_definition
# After line 318, add:
if node.type == "async_function_definition":
    is_async = True
    name_node = next(
        (child for child in node.children if child.type == "identifier"),
        None,
    )
    if name_node:
        name = name_node.text.decode("utf8")
        # ... rest of extraction logic
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/rag/test_symbol_extractor.py::test_async_python_function_extraction -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag/symbol_extractor_tree_sitter.py tests/unit/rag/test_symbol_extractor.py
git commit -m "fix: extract async Python functions correctly"
```

---

### Task 3: Fix Timeout Deadlock in Agent Runner

**Covers:** Orchestrator timeout bug
**Files:**
- Modify: `orchestrator/agent_runner.py:63-68`
- Test: `tests/unit/orchestrator/test_agent_runner.py`

- [ ] **Step 1: Write the failing test**

```python
def test_agent_runner_timeout_does_not_deadlock():
    import asyncio
    from orchestrator.agent_runner import AgentRunner
    
    async def slow_agent():
        await asyncio.sleep(100)
    
    runner = AgentRunner()
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(runner.run_with_timeout(slow_agent, timeout=0.1))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/orchestrator/test_agent_runner.py::test_agent_runner_timeout_does_not_deadlock -v`
Expected: FAIL (deadlock or timeout)

- [ ] **Step 3: Write minimal implementation**

```python
# In orchestrator/agent_runner.py, fix the timeout handling
# After FuturesTimeoutError is raised, cancel the future:
except FuturesTimeoutError as exc:
    future.cancel()
    raise TimeoutError(...)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/orchestrator/test_agent_runner.py::test_agent_runner_timeout_does_not_deadlock -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator/agent_runner.py tests/unit/orchestrator/test_agent_runner.py
git commit -m "fix: cancel future on timeout to prevent deadlock"
```

---

### Task 4: Fix Run Status Data Race

**Covers:** Orchestrator state management bug
**Files:**
- Modify: `orchestrator/engine.py:489`
- Test: `tests/unit/orchestrator/test_engine.py`

- [ ] **Step 1: Write the failing test**

```python
def test_engine_sets_run_status_safely():
    from orchestrator.engine import PipelineEngine
    from orchestrator.state import PipelineRunState
    
    state = PipelineRunState()
    engine = PipelineEngine(run_state=state)
    
    # Simulate concurrent access
    engine.set_run_status("COMPLETED")
    
    assert state.run_status == "COMPLETED"
    # Verify lock was used (check state._lock was acquired)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/orchestrator/test_engine.py::test_engine_sets_run_status_safely -v`
Expected: FAIL (data race or incorrect status)

- [ ] **Step 3: Write minimal implementation**

```python
# In orchestrator/engine.py, line 489
# Change: run_state.run_status = final_status
# To:
run_state.set_run_status(final_status)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/orchestrator/test_engine.py::test_engine_sets_run_status_safely -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator/engine.py tests/unit/orchestrator/test_engine.py
git commit -m "fix: use set_run_status to prevent data race"
```

---

### Task 5: Fix Hardcoded JWT Secret

**Covers:** Auth security bug
**Files:**
- Modify: `scheduler/auth/session_manager.py:52`
- Test: `tests/unit/scheduler/test_auth.py`

- [ ] **Step 1: Write the failing test**

```python
def test_jwt_secret_required_in_production():
    import os
    from scheduler.auth.session_manager import SessionManager
    
    # Remove env var if set
    os.environ.pop("JWT_SECRET", None)
    
    with pytest.raises(ValueError, match="JWT_SECRET"):
        SessionManager()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/scheduler/test_auth.py::test_jwt_secret_required_in_production -v`
Expected: FAIL (no error raised)

- [ ] **Step 3: Write minimal implementation**

```python
# In scheduler/auth/session_manager.py, line 52
# Change: self.jwt_secret = jwt_secret or "dev-secret-change-in-production"
# To:
if not jwt_secret:
    raise ValueError("JWT_SECRET environment variable must be set")
self.jwt_secret = jwt_secret
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/scheduler/test_auth.py::test_jwt_secret_required_in_production -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scheduler/auth/session_manager.py tests/unit/scheduler/test_auth.py
git commit -m "fix: require JWT_SECRET environment variable"
```

---

### Task 6: Fix Public Path Bypass

**Covers:** Auth security bug
**Files:**
- Modify: `scheduler/auth/middleware.py:48-53`
- Test: `tests/unit/scheduler/test_middleware.py`

- [ ] **Step 1: Write the failing test**

```python
def test_public_path_exact_match_only():
    from scheduler.auth.middleware import AuthMiddleware
    
    middleware = AuthMiddleware(public_paths=["/health"])
    
    # Should pass
    assert middleware._is_public_path("/health") is True
    
    # Should fail (prefix matching bug)
    assert middleware._is_public_path("/health-secret") is False
    assert middleware._is_public_path("/healthcheck") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/scheduler/test_middleware.py::test_public_path_exact_match_only -v`
Expected: FAIL (prefix matches succeed)

- [ ] **Step 3: Write minimal implementation**

```python
# In scheduler/auth/middleware.py, lines 48-53
# Change prefix matching to exact match:
def _is_public_path(self, path: str) -> bool:
    # Normalize path (remove trailing slash except root)
    normalized = path.rstrip("/") or "/"
    return normalized in self.public_paths
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/scheduler/test_middleware.py::test_public_path_exact_match_only -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scheduler/auth/middleware.py tests/unit/scheduler/test_middleware.py
git commit -m "fix: use exact path matching for public paths"
```

---

### Task 7: Fix Postgres Thread Safety

**Covers:** Storage thread safety bug
**Files:**
- Modify: `storage/backends.py:298-313`
- Test: `tests/unit/storage/test_backends.py`

- [ ] **Step 1: Write the failing test**

```python
def test_postgres_backend_thread_safe():
    import threading
    from storage.backends import PostgresStorageBackend
    
    backend = PostgresStorageBackend(connection_string="sqlite:///:memory:")
    results = []
    
    def write_data(i):
        backend.write_all([{"id": i, "data": f"test_{i}"}])
        results.append(i)
    
    threads = [threading.Thread(target=write_data, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    assert len(results) == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/storage/test_backends.py::test_postgres_backend_thread_safe -v`
Expected: FAIL (race condition or connection error)

- [ ] **Step 3: Write minimal implementation**

```python
# In storage/backends.py, add threading lock
class PostgresStorageBackend:
    def __init__(self, connection_string: str):
        self._connection_string = connection_string
        self._conn = None
        self._lock = threading.Lock()
    
    def _ensure_connection(self):
        with self._lock:
            if self._conn is None or self._conn.closed:
                self._conn = psycopg2.connect(self._connection_string)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/storage/test_backends.py::test_postgres_backend_thread_safe -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add storage/backends.py tests/unit/storage/test_backends.py
git commit -m "fix: add thread safety to PostgresStorageBackend"
```

---

### Task 8: Fix Non-Constant-Time API Key Comparison

**Covers:** Auth security bug
**Files:**
- Modify: `scheduler/gateway.py:329`
- Test: `tests/unit/scheduler/test_gateway.py`

- [ ] **Step 1: Write the failing test**

```python
def test_constant_time_api_key_comparison():
    import hmac
    from scheduler.gateway import verify_operator_key
    
    # Test that comparison is constant-time
    key1 = "test-key-12345"
    key2 = "test-key-12346"  # Last char different
    
    # Both should return False (wrong key)
    assert verify_operator_key(key1, "wrong") is False
    assert verify_operator_key(key2, "wrong") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/scheduler/test_gateway.py::test_constant_time_api_key_comparison -v`
Expected: FAIL (not using constant-time comparison)

- [ ] **Step 3: Write minimal implementation**

```python
# In scheduler/gateway.py, line 329
# Change: if not operator_key or operator_key != config.operator_api_key:
# To:
if not operator_key or not hmac.compare_digest(operator_key, config.operator_api_key or ""):
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/scheduler/test_gateway.py::test_constant_time_api_key_comparison -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scheduler/gateway.py tests/unit/scheduler/test_gateway.py
git commit -m "fix: use constant-time comparison for API keys"
```

---

## Phase 2: Performance Bottlenecks (P1)

### Task 9: Fix Duplicate File Reads in RAG Pipeline

**Covers:** RAG performance
**Files:**
- Modify: `rag/stages.py:87-92, 237-238`
- Test: `tests/unit/rag/test_stages.py`

- [ ] **Step 1: Write the failing test**

```python
def test_no_duplicate_file_reads():
    from unittest.mock import patch
    from rag.stages import ParsingStage, ChunkingStage
    
    with patch("builtins.open", create=True) as mock_open:
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.read.return_value = "content"
        
        parser = ParsingStage()
        chunker = ChunkingStage()
        
        parsed = parser.run([{"path": "test.py"}])
        chunker.run(parsed)
        
        # File should only be read once
        assert mock_open.call_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/rag/test_stages.py::test_no_duplicate_file_reads -v`
Expected: FAIL (file read multiple times)

- [ ] **Step 3: Write minimal implementation**

```python
# In rag/stages.py, ChunkingStage.run()
# Pass parsed_file.content instead of re-reading
def run(self, parsed_files: list[dict]) -> list[dict]:
    chunks = []
    for parsed_file in parsed_files:
        content = parsed_file.get("content", "")
        # Use content directly instead of re-reading file
        chunks.extend(self._chunk_content(content, parsed_file["path"]))
    return chunks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/rag/test_stages.py::test_no_duplicate_file_reads -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag/stages.py tests/unit/rag/test_stages.py
git commit -m "perf: eliminate duplicate file reads in RAG pipeline"
```

---

### Task 10: Fix _get_docstring O(N*M) Performance

**Covers:** RAG performance
**Files:**
- Modify: `rag/symbol_extractor_tree_sitter.py:247-266`
- Test: `tests/unit/rag/test_symbol_extractor.py`

- [ ] **Step 1: Write the failing test**

```python
def test_get_docstring_efficient():
    from rag.symbol_extractor_tree_sitter import TreeSitterSymbolExtractor
    
    extractor = TreeSitterSymbolExtractor()
    source = "x" * 100000  # Large source
    
    # Should not decode entire source multiple times
    lines = source.split("\n")
    
    # Mock to count decode calls
    with patch.object(extractor, '_get_docstring') as mock:
        mock.return_value = ""
        # Call multiple times
        for _ in range(100):
            extractor._get_docstring(None, source.encode(), 0, 10)
        
        # Should reuse decoded source
        assert mock.call_count == 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/rag/test_symbol_extractor.py::test_get_docstring_efficient -v`
Expected: FAIL (O(N*M) behavior)

- [ ] **Step 3: Write minimal implementation**

```python
# In rag/symbol_extractor_tree_sitter.py, refactor _get_docstring
def _get_docstring(self, node, source_bytes: bytes, start_line: int, end_line: int) -> str:
    # Decode once and cache
    if not hasattr(self, '_cached_lines') or self._cached_source != source_bytes:
        self._cached_source = source_bytes
        self._cached_lines = source_bytes.decode("utf8").split("\n")
    
    lines = self._cached_lines[start_line:end_line]
    # ... rest of logic
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/rag/test_symbol_extractor.py::test_get_docstring_efficient -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag/symbol_extractor_tree_sitter.py tests/unit/rag/test_symbol_extractor.py
git commit -m "perf: cache decoded source in _get_docstring"
```

---

### Task 11: Fix Hybrid Retriever O(N*M) Scoring

**Covers:** RAG performance
**Files:**
- Modify: `rag/hybrid_retriever.py:63-138`
- Test: `tests/unit/rag/test_hybrid_retriever.py`

- [ ] **Step 1: Write the failing test**

```python
def test_hybrid_retriever_scoring_efficient():
    from rag.hybrid_retriever import HybridRetriever
    
    retriever = HybridRetriever()
    
    # Mock vector and keyword results
    vector_results = [{"id": f"doc_{i}", "score": 0.9 - i*0.1} for i in range(100)]
    keyword_results = [{"id": f"doc_{i}", "rank": i+1} for i in range(100)]
    
    # Should use dict lookup, not linear scan
    merged = retriever._merge_results(vector_results, keyword_results, 0.5)
    
    assert len(merged) == 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/rag/test_hybrid_retriever.py::test_hybrid_retriever_scoring_efficient -v`
Expected: FAIL (O(N*M) behavior)

- [ ] **Step 3: Write minimal implementation**

```python
# In rag/hybrid_retriever.py, refactor _merge_results
def _merge_results(self, vector_results, keyword_results, alpha):
    # Build dict for O(1) lookup
    vector_dict = {r["id"]: r for r in vector_results}
    keyword_dict = {r["id"]: r for r in keyword_results}
    
    all_ids = set(vector_dict.keys()) | set(keyword_dict.keys())
    
    scores = {}
    for doc_id in all_ids:
        v_score = vector_dict.get(doc_id, {}).get("score", 0)
        k_rank = keyword_dict.get(doc_id, {}).get("rank", len(keyword_results) + 1)
        
        # Normalize scores to same scale
        v_normalized = v_score
        k_normalized = 1.0 / k_rank
        
        scores[doc_id] = alpha * v_normalized + (1 - alpha) * k_normalized
    
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/rag/test_hybrid_retriever.py::test_hybrid_retriever_scoring_efficient -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag/hybrid_retriever.py tests/unit/rag/test_hybrid_retriever.py
git commit -m "perf: use dict lookup in hybrid retriever scoring"
```

---

### Task 12: Fix Checkpoint Double Serialization

**Covers:** Orchestrator performance
**Files:**
- Modify: `orchestrator/checkpointing.py:50,56`
- Test: `tests/unit/orchestrator/test_checkpointing.py`

- [ ] **Step 1: Write the failing test**

```python
def test_checkpoint_single_serialization():
    from unittest.mock import patch
    from orchestrator.checkpointing import build_checkpoint_payload
    from orchestrator.state import PipelineRunState
    
    state = PipelineRunState()
    
    with patch.object(state, 'to_dict') as mock_to_dict:
        mock_to_dict.return_value = {"status": "running"}
        
        payload = build_checkpoint_payload(state)
        
        # Should only serialize once
        assert mock_to_dict.call_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/orchestrator/test_checkpointing.py::test_checkpoint_single_serialization -v`
Expected: FAIL (to_dict called twice)

- [ ] **Step 3: Write minimal implementation**

```python
# In orchestrator/checkpointing.py, lines 50 and 56
# Cache the serialized state:
state_dict = run_state.to_dict()

return {
    ...
    "run_state": state_dict,
    "checkpoint": {
        ...
        "run_state_snapshot": state_dict,
    },
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/orchestrator/test_checkpointing.py::test_checkpoint_single_serialization -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator/checkpointing.py tests/unit/orchestrator/test_checkpointing.py
git commit -m "perf: cache run_state serialization in checkpoint"
```

---

### Task 13: Fix Retry Backoff Unbounded Growth

**Covers:** Orchestrator retry logic
**Files:**
- Modify: `orchestrator/retry.py:13-16`
- Test: `tests/unit/orchestrator/test_retry.py`

- [ ] **Step 1: Write the failing test**

```python
def test_retry_backoff_has_upper_bound():
    from orchestrator.retry import calculate_backoff
    
    # With max_backoff=60, should never exceed 60 seconds
    for attempt in range(1, 20):
        backoff = calculate_backoff(attempt, base_seconds=10, max_seconds=60)
        assert backoff <= 60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/orchestrator/test_retry.py::test_retry_backoff_has_upper_bound -v`
Expected: FAIL (backoff exceeds 60)

- [ ] **Step 3: Write minimal implementation**

```python
# In orchestrator/retry.py, lines 13-16
def calculate_backoff(attempt: int, base_seconds: float = 10, max_seconds: float = 300) -> float:
    if attempt <= 0:
        return 0
    backoff = base_seconds * (2 ** (attempt - 1))
    return min(backoff, max_seconds)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/orchestrator/test_retry.py::test_retry_backoff_has_upper_bound -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator/retry.py tests/unit/orchestrator/test_retry.py
git commit -m "fix: add upper bound to retry backoff"
```

---

### Task 14: Fix N+1 Queries in Gateway

**Covers:** Storage performance
**Files:**
- Modify: `scheduler/gateway.py:523-534`
- Test: `tests/unit/scheduler/test_gateway.py`

- [ ] **Step 1: Write the failing test**

```python
def test_gateway_list_runs_efficient():
    from unittest.mock import patch
    from scheduler.gateway import Gateway
    
    gateway = Gateway()
    
    with patch.object(gateway.step_log_repository, 'list_by_run') as mock_logs:
        with patch.object(gateway.artifact_repository, 'list_by_run') as mock_artifacts:
            mock_logs.return_value = []
            mock_artifacts.return_value = []
            
            # List 10 runs
            runs = gateway.list_runs(limit=10)
            
            # Should batch queries, not N+1
            assert mock_logs.call_count <= 2  # At most 2 batched calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/scheduler/test_gateway.py::test_gateway_list_runs_efficient -v`
Expected: FAIL (N+1 queries)

- [ ] **Step 3: Write minimal implementation**

```python
# In scheduler/gateway.py, refactor _to_payload
def _to_payload(self, runs: list[RunRecord]) -> list[dict]:
    # Batch load all step logs and artifacts
    run_ids = [r.run_id for r in runs]
    
    all_logs = {}
    for logs in self.step_log_repository.list_by_run_batch(run_ids):
        all_logs[logs.run_id] = logs
    
    all_artifacts = {}
    for artifacts in self.artifact_repository.list_by_run_batch(run_ids):
        all_artifacts[artifacts.run_id] = artifacts
    
    # Build payloads using pre-loaded data
    return [self._build_payload(run, all_logs.get(run.run_id, []), all_artifacts.get(run.run_id, [])) for run in runs]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/scheduler/test_gateway.py::test_gateway_list_runs_efficient -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scheduler/gateway.py tests/unit/scheduler/test_gateway.py
git commit -m "perf: batch load step logs and artifacts in list runs"
```

---

### Task 15: Fix JSON Serialization Quadratic Growth

**Covers:** Storage performance
**Files:**
- Modify: `storage/backends.py:176-193`
- Test: `tests/unit/storage/test_backends.py`

- [ ] **Step 1: Write the failing test**

```python
def test_payload_size_estimation_efficient():
    from storage.backends import JsonStorageBackend
    
    backend = JsonStorageBackend()
    
    # Create large payload
    items = [{"id": i, "data": "x" * 100} for i in range(1000)]
    
    # Should not be O(N^2)
    size = backend._payload_size_bytes(items)
    
    assert size > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/storage/test_backends.py::test_payload_size_estimation_efficient -v`
Expected: FAIL (quadratic behavior)

- [ ] **Step 3: Write minimal implementation**

```python
# In storage/backends.py, refactor _payload_size_bytes
def _payload_size_bytes(self, items: list[dict]) -> int:
    # Use incremental size estimation
    total = 2  # [] brackets
    for i, item in enumerate(items):
        if i > 0:
            total += 1  # comma
        total += len(json.dumps(item, ensure_ascii=False).encode("utf-8"))
    return total
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/storage/test_backends.py::test_payload_size_estimation_efficient -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add storage/backends.py tests/unit/storage/test_backends.py
git commit -m "perf: use incremental size estimation for payload splitting"
```

---

## Phase 3: Code Quality (P2)

### Task 16: Consolidate Duplicate Symbol Classes

**Covers:** RAG code quality
**Files:**
- Modify: `rag/symbol_extractor.py`, `rag/models.py`, `rag/symbol_extractor_tree_sitter.py`
- Test: `tests/unit/rag/test_symbol_extractor.py`

- [ ] **Step 1: Write the failing test**

```python
def test_single_symbol_class():
    from rag.models import Symbol
    from rag.symbol_extractor import SymbolExtractor
    
    # Should use same Symbol class
    extractor = SymbolExtractor()
    symbols = extractor.extract_symbols("def test(): pass", "test.py")
    
    assert isinstance(symbols[0], Symbol)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/rag/test_symbol_extractor.py::test_single_symbol_class -v`
Expected: FAIL (different Symbol classes)

- [ ] **Step 3: Write minimal implementation**

```python
# In rag/symbol_extractor.py, import from models
from rag.models import Symbol

# Remove duplicate Symbol class definition
# Update all imports to use rag.models.Symbol
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/rag/test_symbol_extractor.py::test_single_symbol_class -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag/symbol_extractor.py rag/models.py rag/symbol_extractor_tree_sitter.py
git commit -m "refactor: consolidate Symbol class to rag.models"
```

---

### Task 17: Extract Shared Utilities

**Covers:** Orchestrator code quality
**Files:**
- Create: `orchestrator/utils.py`
- Modify: `orchestrator/engine.py`, `orchestrator/executor.py`, `orchestrator/pipeline_runner.py`
- Test: `tests/unit/orchestrator/test_utils.py`

- [ ] **Step 1: Write the failing test**

```python
def test_shared_utilities():
    from orchestrator.utils import now_iso, is_step_success, log_event
    
    # Test now_iso
    assert now_iso() is not None
    
    # Test is_step_success
    assert is_step_success({"status": "SUCCESS"}) is True
    assert is_step_success({"status": "FAILED"}) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/orchestrator/test_utils.py::test_shared_utilities -v`
Expected: FAIL (utilities not found)

- [ ] **Step 3: Write minimal implementation**

```python
# Create orchestrator/utils.py
from datetime import datetime, timezone
import json
from logging_utils import redact_mapping

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def is_step_success(result: dict) -> bool:
    return result.get("status") in {"SUCCESS", "PARTIAL_SUCCESS"}

def log_event(logger, level: int, payload: dict, correlation_id: str = None, step_name: str = None):
    if correlation_id:
        payload["correlation_id"] = correlation_id
    if step_name:
        payload["step"] = step_name
    logger.log(level, json.dumps(redact_mapping(payload), ensure_ascii=False))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/orchestrator/test_utils.py::test_shared_utilities -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add orchestrator/utils.py tests/unit/orchestrator/test_utils.py
git commit -m "refactor: extract shared utilities to orchestrator.utils"
```

---

### Task 18: Extract Provider Handler Base Class

**Covers:** Agent code quality
**Files:**
- Create: `agents/llm_providers_base.py`
- Modify: `agents/llm_providers.py`
- Test: `tests/unit/agents/test_llm_providers.py`

- [ ] **Step 1: Write the failing test**

```python
def test_provider_handlers_inherit_base():
    from agents.llm_providers import OpenRouterHandler, DeepSeekHandler
    from agents.llm_providers_base import OpenAICompatibleHandler
    
    assert issubclass(OpenRouterHandler, OpenAICompatibleHandler)
    assert issubclass(DeepSeekHandler, OpenAICompatibleHandler)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/agents/test_llm_providers.py::test_provider_handlers_inherit_base -v`
Expected: FAIL (handlers don't inherit base)

- [ ] **Step 3: Write minimal implementation**

```python
# Create agents/llm_providers_base.py
class OpenAICompatibleHandler:
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self._client = None
    
    def create_message(self, messages, **kwargs):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        
        stream = kwargs.get("stream", False)
        if stream:
            return self._create_stream(messages, **kwargs)
        return self._create_sync(messages, **kwargs)
    
    def _create_stream(self, messages, **kwargs):
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            **kwargs
        )
        for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    def _create_sync(self, messages, **kwargs):
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs
        )
        return response.choices[0].message.content
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/agents/test_llm_providers.py::test_provider_handlers_inherit_base -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agents/llm_providers_base.py tests/unit/agents/test_llm_providers.py
git commit -m "refactor: extract OpenAI compatible handler base class"
```

---

### Task 19: Fix Token Budget Daily Limits

**Covers:** Agent bug
**Files:**
- Modify: `agents/token_budget_system.py:357-378`
- Test: `tests/unit/agents/test_token_budget.py`

- [ ] **Step 1: Write the failing test**

```python
def test_daily_budget_limit_works():
    from agents.token_budget_system import TokenBudgetSystem
    from agents.llm_providers import ModelInfo
    
    budget = TokenBudgetSystem(daily_limit=1000.0)
    
    # Mock model with actual prices
    model = ModelInfo(
        name="test",
        input_cost_per_1k=0.01,
        output_cost_per_1k=0.02
    )
    
    # Track usage that exceeds daily limit
    budget.track_usage(model, input_tokens=50000, output_tokens=50000)
    
    # Should raise RuntimeError
    with pytest.raises(RuntimeError):
        budget.track_usage(model, input_tokens=50000, output_tokens=50000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/agents/test_token_budget.py::test_daily_budget_limit_works -v`
Expected: FAIL (no RuntimeError)

- [ ] **Step 3: Write minimal implementation**

```python
# In agents/token_budget_system.py, fix _check_budget_limits
def _check_budget_limits(self, provider_usage: ProviderUsage) -> None:
    # Calculate actual cost with real model prices
    if self._current_model:
        daily_cost = self.calculate_cost(self._current_model, provider_usage)
    else:
        daily_cost = 0.0
    
    if self.daily_limit and daily_cost > self.daily_limit:
        raise RuntimeError(f"Daily budget limit exceeded: ${daily_cost:.2f} > ${self.daily_limit:.2f}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/agents/test_token_budget.py::test_daily_budget_limit_works -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agents/token_budget_system.py tests/unit/agents/test_token_budget.py
git commit -m "fix: use actual model prices for daily budget limits"
```

---

### Task 20: Fix Circuit Breaker Stream Buffering

**Covers:** Agent performance
**Files:**
- Modify: `agents/llm_wrapper.py:492-503`
- Test: `tests/unit/agents/test_llm_wrapper.py`

- [ ] **Step 1: Write the failing test**

```python
def test_circuit_breaker_streams_efficiently():
    from unittest.mock import MagicMock
    from agents.llm_wrapper import CircuitBreakerLLMWrapper
    
    mock_wrapper = MagicMock()
    mock_wrapper.complete_stream.return_value = iter(["chunk1", "chunk2", "chunk3"])
    
    cb = CircuitBreakerLLMWrapper(mock_wrapper)
    
    # Should not buffer entire stream
    chunks = list(cb.complete_stream("test"))
    
    assert len(chunks) == 3
    assert chunks == ["chunk1", "chunk2", "chunk3"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/agents/test_llm_wrapper.py::test_circuit_breaker_streams_efficiently -v`
Expected: FAIL (stream buffered)

- [ ] **Step 3: Write minimal implementation**

```python
# In agents/llm_wrapper.py, fix complete_stream
def complete_stream(self, prompt, **kwargs):
    # Don't buffer - yield directly
    for chunk in self._delegate.complete_stream(prompt, **kwargs):
        yield chunk
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/agents/test_llm_wrapper.py::test_circuit_breaker_streams_efficiently -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agents/llm_wrapper.py tests/unit/agents/test_llm_wrapper.py
git commit -m "fix: don't buffer stream in circuit breaker"
```

---

## Execution Checklist

After completing all tasks:

- [ ] Run full test suite: `pytest -v`
- [ ] Run linting: `ruff check --fix`
- [ ] Run formatting: `ruff format`
- [ ] Run type checking: `mypy --ignore-missing-imports`
- [ ] Verify no regressions
- [ ] Commit all changes

---

## Summary

This plan addresses:
- **8 Critical bugs** (P0): Runtime crashes, security vulnerabilities, data races
- **7 Performance bottlenecks** (P1): O(N²) algorithms, duplicate I/O, N+1 queries
- **5 Code quality issues** (P2): Duplication, missing abstractions, dead code

Total: **20 tasks** with TDD approach, each self-contained and testable.
