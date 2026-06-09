import asyncio
import os
import sys
import tempfile
from pathlib import Path
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.librarian import (
    LibrarianAgent, get_librarian_agent,
    ELIGIBLE_EXTENSIONS, EXCLUDE_DIRS, MAX_FILES,
)
from agents.base import AgentRequest


class TestLibrarianAgent:
    @pytest.mark.asyncio
    async def test_initial_status(self):
        agent = LibrarianAgent()
        assert agent.name == "librarian"
        assert agent.is_indexed is False
        assert agent.file_count == 0

    @pytest.mark.asyncio
    async def test_scan_small_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_cwd = Path.cwd()
            os.chdir(tmpdir)

            (Path(tmpdir) / "main.py").write_text("print('hello')\n")
            (Path(tmpdir) / "config.json").write_text('{"key": "value"}\n')
            (Path(tmpdir) / "README.md").write_text("# Test\n")
            (Path(tmpdir) / ".gitignore").write_text("*.pyc\n")

            (Path(tmpdir) / ".git").mkdir()
            (Path(tmpdir) / ".git" / "config").write_text("[core]\n")

            (Path(tmpdir) / "node_modules").mkdir()
            (Path(tmpdir) / "node_modules" / "pkg.js").write_text("skip me\n")

            agent = LibrarianAgent()
            agent._project_root = Path(tmpdir)
            await agent._scan_project()

            assert agent.is_indexed is True
            assert agent.file_count > 0
            for f in agent._files:
                assert ".git" not in f["path"]
                assert "node_modules" not in f["path"]

            os.chdir(orig_cwd)

    @pytest.mark.asyncio
    async def test_tokenize(self):
        agent = LibrarianAgent()
        tokens = agent._tokenize("src/components/MyComponent.tsx")
        assert "src" in tokens
        assert "components" in tokens

    @pytest.mark.asyncio
    async def test_search_basic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_cwd = Path.cwd()
            os.chdir(tmpdir)

            (Path(tmpdir) / "app.py").write_text("import flask\napp = Flask(__name__)\n")
            (Path(tmpdir) / "utils.py").write_text("def helper():\n    pass\n")

            agent = LibrarianAgent()
            agent._project_root = Path(tmpdir)
            await agent._scan_project()

            matches = agent._search("app")
            assert len(matches) > 0
            assert any("app.py" in m["path"] for m in matches)

            os.chdir(orig_cwd)

    @pytest.mark.asyncio
    async def test_search_returns_up_to_10_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_cwd = Path.cwd()
            os.chdir(tmpdir)

            for i in range(20):
                (Path(tmpdir) / f"file_{i}.py").write_text(f"# file {i}\n")

            agent = LibrarianAgent()
            agent._project_root = Path(tmpdir)
            await agent._scan_project()

            matches = agent._search("file_")
            assert len(matches) <= 10

            os.chdir(orig_cwd)

    @pytest.mark.asyncio
    async def test_filters_binary_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_cwd = Path.cwd()
            os.chdir(tmpdir)

            (Path(tmpdir) / "main.py").write_text("print('hello')\n")
            (Path(tmpdir) / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")

            agent = LibrarianAgent()
            agent._project_root = Path(tmpdir)
            await agent._scan_project()

            assert agent.file_count == 1
            assert not any("image.png" in f["path"] for f in agent._files)

            os.chdir(orig_cwd)

    @pytest.mark.asyncio
    async def test_empty_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_cwd = Path.cwd()
            os.chdir(tmpdir)

            agent = LibrarianAgent()
            agent._project_root = Path(tmpdir)
            await agent._scan_project()

            assert agent.is_indexed is True
            assert agent.file_count == 0

            os.chdir(orig_cwd)

    @pytest.mark.asyncio
    async def test_process_uninitialized(self):
        agent = LibrarianAgent()
        req = AgentRequest(request_id="test", command="search", data={"query": "test"})
        response = await agent.process(req)
        assert response.status == "not_ready"

    @pytest.mark.asyncio
    async def test_process_empty_query(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_cwd = Path.cwd()
            os.chdir(tmpdir)
            (Path(tmpdir) / "main.py").write_text("print('hello')\n")

            agent = LibrarianAgent()
            agent._project_root = Path(tmpdir)
            await agent._scan_project()

            req = AgentRequest(request_id="test", command="search", data={"query": ""})
            response = await agent.process(req)
            assert response.status == "ok"
            assert response.data["matches"] == []

            os.chdir(orig_cwd)

    @pytest.mark.asyncio
    async def test_eligible_extensions(self):
        agent = LibrarianAgent()
        assert ".py" in ELIGIBLE_EXTENSIONS
        assert ".js" in ELIGIBLE_EXTENSIONS
        assert ".md" in ELIGIBLE_EXTENSIONS
        assert ".json" in ELIGIBLE_EXTENSIONS

    @pytest.mark.asyncio
    async def test_exclude_dirs(self):
        assert ".git" in EXCLUDE_DIRS
        assert "node_modules" in EXCLUDE_DIRS
        assert "__pycache__" in EXCLUDE_DIRS

    @pytest.mark.asyncio
    async def test_get_librarian_agent(self):
        agent = get_librarian_agent()
        assert agent is not None
        assert isinstance(agent, LibrarianAgent)


    @pytest.mark.asyncio
    async def test_remove_from_index(self):
        agent = LibrarianAgent()
        agent._files = [
            {"path": "src/main.py", "size": 10, "ext": ".py", "snippet": "print"},
            {"path": "src/utils.py", "size": 20, "ext": ".py", "snippet": "def util"},
            {"path": "src/app.py", "size": 30, "ext": ".py", "snippet": "import app"},
        ]
        agent._build_index()
        assert len(agent._files) == 3
        assert len(agent._index) > 0

        agent._remove_file("src/main.py")
        assert len(agent._files) == 2
        assert agent._files[0]["path"] == "src/utils.py"
        assert agent._files[1]["path"] == "src/app.py"

    @pytest.mark.asyncio
    async def test_remove_from_index_not_found(self):
        agent = LibrarianAgent()
        agent._files = [{"path": "src/main.py", "size": 10, "ext": ".py", "snippet": "print"}]
        agent._build_index()
        agent._remove_file("nonexistent.py")
        assert len(agent._files) == 1

    @pytest.mark.asyncio
    async def test_rebuild_index(self):
        agent = LibrarianAgent()
        agent._files = [
            {"path": "src/main.py", "size": 10, "ext": ".py", "snippet": "print('hello')"},
            {"path": "src/utils.py", "size": 20, "ext": ".py", "snippet": "def helper():"},
        ]
        agent._build_index()
        assert "main" in agent._index or "src" in agent._index

        agent._files.pop(0)
        agent._rebuild_index()
        assert len(agent._files) == 1

    @pytest.mark.asyncio
    async def test_watchdog_worker_processes_events(self):
        agent = LibrarianAgent()
        agent._project_root = Path(tempfile.mkdtemp())
        (agent._project_root / "test.py").write_text("print('original')\n")
        agent._files = []
        agent._ready = True

        agent._scan_task = asyncio.create_task(asyncio.sleep(0))
        agent._watchdog_task = asyncio.create_task(agent._watchdog_worker())
        await asyncio.sleep(0.05)

        path = str(agent._project_root / "test.py")
        agent._watchdog_queue.put_nowait(("modified", path))
        await asyncio.sleep(1.5)

        assert len(agent._files) > 0
        assert agent._files[0]["path"] == "test.py"

        agent._watchdog_task.cancel()
        try: await agent._watchdog_task
        except: pass

    @pytest.mark.asyncio
    async def test_watchdog_worker_handles_deleted_file(self):
        agent = LibrarianAgent()
        agent._project_root = Path(tempfile.mkdtemp())
        agent._files.append({
            "path": "main.py", "size": 15, "ext": ".py", "snippet": "print('hello')"
        })
        agent._build_index()
        agent._ready = True

        agent._scan_task = asyncio.create_task(asyncio.sleep(0))
        agent._watchdog_task = asyncio.create_task(agent._watchdog_worker())
        await asyncio.sleep(0.05)

        assert len(agent._files) == 1
        path = str(agent._project_root / "main.py")
        agent._watchdog_queue.put_nowait(("deleted", path))
        await asyncio.sleep(1.5)

        assert len(agent._files) == 0

        agent._watchdog_task.cancel()
        try: await agent._watchdog_task
        except: pass

    @pytest.mark.asyncio
    async def test_librarian_file_handler_queues_events(self):
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        from agents.librarian import _LibrarianFileHandler
        from watchdog.events import FileModifiedEvent, FileCreatedEvent, FileDeletedEvent, FileMovedEvent

        handler = _LibrarianFileHandler(queue, loop)

        handler.on_modified(FileModifiedEvent("/tmp/test.py"))
        await asyncio.sleep(0)
        assert queue.qsize() == 1
        event_type, path = queue.get_nowait()
        assert event_type == "modified"
        assert path == "/tmp/test.py"

        handler.on_created(FileCreatedEvent("/tmp/new.py"))
        await asyncio.sleep(0)
        assert queue.qsize() == 1
        event_type, path = queue.get_nowait()
        assert event_type == "created"

        handler.on_deleted(FileDeletedEvent("/tmp/old.py"))
        await asyncio.sleep(0)
        assert queue.qsize() == 1
        event_type, path = queue.get_nowait()
        assert event_type == "deleted"

        handler.on_moved(FileMovedEvent("/tmp/src.py", "/tmp/dst.py"))
        await asyncio.sleep(0)
        assert queue.qsize() == 2
        e1, p1 = queue.get_nowait()
        e2, p2 = queue.get_nowait()
        assert e1 == "deleted" and p1 == "/tmp/src.py"
        assert e2 == "created" and p2 == "/tmp/dst.py"

    def test_watchdog_available(self):
        from agents.librarian import _HAS_WATCHDOG
        assert _HAS_WATCHDOG is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
