from agents.memory_agent import MemoryAgent, retrieve_context, setup_memory, store_context


class TestMemoryStorageSetup:
    def test_setup_memory_success(self, tmp_path):
        assert (
            setup_memory({"type": "json", "file_path": str(tmp_path / "test_memory.json")})[
                "status"
            ]
            == "ready"
        )

    def test_setup_memory_failure(self):
        assert setup_memory({"type": "invalid"})["status"] == "failed"


class TestContextRetrieval:
    def test_retrieve_context_success(self, tmp_path):
        setup_memory({"type": "json", "file_path": str(tmp_path / "memory.json")})
        assert store_context({"data": "test_data", "context_id": "ctx_123"})["status"] == "success"
        result = retrieve_context("ctx_123")
        assert result["status"] == "success"
        assert "context" in result

    def test_retrieve_context_not_found(self, tmp_path):
        setup_memory({"type": "json", "file_path": str(tmp_path / "memory.json")})
        assert retrieve_context("nonexistent")["status"] == "not_found"


class TestContextStorage:
    def test_store_context_success(self, tmp_path):
        setup_memory({"type": "json", "file_path": str(tmp_path / "memory.json")})
        result = store_context({"data": "test"})
        assert result["status"] == "success"
        assert "context_id" in result

    def test_store_context_failure(self):
        assert store_context({})["status"] == "failed"


class TestMemoryAgentModes:
    def test_seed_mode(self):
        result = MemoryAgent().run({"repository": {"full_name": "org/repo"}})
        assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
        assert result["artifacts"][0]["content"]["quality_signals"]["memory_mode"] == "seed"

    def test_retrieve_mode_with_query(self):
        context = {
            "query": "auth logic",
            "rag_initializer": {
                "artifacts": [
                    {
                        "type": "rag_index",
                        "content": {
                            "documents": [
                                {
                                    "path": "auth.py",
                                    "summary": "Authentication helpers",
                                    "content": "auth logic",
                                }
                            ],
                            "documents_count": 1,
                            "collection_name": "repo_chunks",
                        },
                    }
                ]
            },
        }
        result = MemoryAgent().run(context)
        assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
        assert result["artifacts"][0]["content"]["quality_signals"]["memory_mode"] == "retrieve"

    def test_write_mode_persists(self, tmp_path):
        setup_memory({"type": "json", "file_path": str(tmp_path / "memory.json")})
        result = MemoryAgent().run(
            {
                "task_description": "Fix auth bug",
                "result": {"status": "SUCCESS"},
                "code_patch": {"files": [{"path": "auth.py", "content": "print(1)"}]},
            }
        )
        assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}
        artifact = result["artifacts"][0]["content"]
        assert artifact["quality_signals"]["memory_mode"] == "write"
        assert artifact["quality_signals"]["write_persisted"] is True

    def test_retrieve_mode_includes_persisted_memory_store_matches(self, tmp_path):
        setup_memory({"type": "json", "file_path": str(tmp_path / "memory.json")})
        assert (
            store_context(
                {
                    "task_description": "Fix auth token validation in login endpoint",
                    "result": {"status": "SUCCESS"},
                    "code_patch": {"files": [{"path": "auth.py", "diff": "..."}]},
                    "entry_type": "task",
                }
            )["status"]
            == "success"
        )

        result = MemoryAgent().run({"query": "auth token validation"})
        assert result["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}

        matches = result["artifacts"][0]["content"]["matches"]
        assert any(item.get("source") == "memory_store" for item in matches)

    def test_write_mode_with_fallback_patch_does_not_persist(self, tmp_path):
        setup_memory({"type": "json", "file_path": str(tmp_path / "memory.json")})
        result = MemoryAgent().run(
            {
                "task_description": "Fix flaky test",
                "result": {"status": "SUCCESS"},
            }
        )

        assert result["status"] in {"PARTIAL_SUCCESS", "BLOCKED"}
        artifact = result["artifacts"][0]["content"]
        assert artifact["quality_signals"]["memory_mode"] == "write"
        assert artifact["quality_signals"]["write_persisted"] is False
