import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from enum import Enum
from abc import ABC, abstractmethod

logger = logging.getLogger("shellmate.agents")


class AgentStatus(Enum):
    STARTING = "starting"
    READY = "ready"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class AgentRequest:
    request_id: str
    command: str
    data: Dict[str, Any] = field(default_factory=dict)
    timeout: float = 5.0


@dataclass
class AgentResponse:
    request_id: str
    agent_name: str
    status: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    latency_ms: float = 0.0


class Agent(ABC):
    def __init__(self, name: str):
        self.name = name
        self._status = AgentStatus.STARTING
        self._request_queue: asyncio.Queue = asyncio.Queue()
        self._response_futures: Dict[str, asyncio.Future] = {}
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None

    @property
    def status(self) -> AgentStatus:
        return self._status

    @abstractmethod
    async def initialize(self) -> None:
        pass

    @abstractmethod
    async def process(self, request: AgentRequest) -> AgentResponse:
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        pass

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        await self.initialize()
        self._status = AgentStatus.READY
        self._worker_task = asyncio.create_task(self._worker())
        logger.info(f"Agent {self.name} started")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        await self.shutdown()
        self._status = AgentStatus.STOPPED
        logger.info(f"Agent {self.name} stopped")

    async def _worker(self) -> None:
        while self._running:
            try:
                request = await asyncio.wait_for(
                    self._request_queue.get(), timeout=1.0
                )
                await self._handle_request(request)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Agent {self.name} worker error: {e}", exc_info=True)

    async def _handle_request(self, request: AgentRequest) -> None:
        response_future = self._response_futures.get(request.request_id)
        if not response_future:
            logger.warning(f"Agent {self.name}: No response future for request {request.request_id}")
            return

        start_time = asyncio.get_event_loop().time()
        try:
            response = await asyncio.wait_for(
                self.process(request), timeout=request.timeout
            )
        except asyncio.TimeoutError:
            response = AgentResponse(
                request_id=request.request_id,
                agent_name=self.name,
                status="timeout",
                error=f"Agent {self.name} timed out after {request.timeout}s",
                latency_ms=(asyncio.get_event_loop().time() - start_time) * 1000,
            )
        except Exception as e:
            logger.error(f"Agent {self.name} process error: {e}", exc_info=True)
            response = AgentResponse(
                request_id=request.request_id,
                agent_name=self.name,
                status="error",
                error=str(e),
                latency_ms=(asyncio.get_event_loop().time() - start_time) * 1000,
            )
        else:
            response.latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000

        if not response_future.done():
            response_future.set_result(response)

    async def send_request(self, command: str, data: Dict[str, Any] = None, timeout: float = 5.0) -> AgentResponse:
        if not self._running or self._status != AgentStatus.READY:
            return AgentResponse(
                request_id=str(uuid.uuid4()),
                agent_name=self.name,
                status="error",
                error=f"Agent {self.name} not ready",
            )

        request_id = str(uuid.uuid4())
        request = AgentRequest(
            request_id=request_id,
            command=command,
            data=data or {},
            timeout=timeout,
        )

        response_future = asyncio.get_running_loop().create_future()
        self._response_futures[request_id] = response_future

        try:
            await self._request_queue.put(request)
            response = await asyncio.wait_for(response_future, timeout=timeout + 1.0)
            return response
        except asyncio.TimeoutError:
            if not response_future.done():
                response_future.cancel()
            return AgentResponse(
                request_id=request_id,
                agent_name=self.name,
                status="timeout",
                error=f"Request timed out after {timeout}s",
            )
        finally:
            self._response_futures.pop(request_id, None)


class AgentManager:
    def __init__(self):
        self._agents: Dict[str, Agent] = {}
        self._running = False

    def register(self, agent: Agent) -> None:
        self._agents[agent.name] = agent

    def get(self, name: str) -> Optional[Agent]:
        return self._agents.get(name)

    async def start_all(self) -> None:
        if self._running:
            return
        self._running = True
        for agent in self._agents.values():
            await agent.start()
        logger.info("All agents started")

    async def stop_all(self) -> None:
        if not self._running:
            return
        for agent in self._agents.values():
            await agent.stop()
        self._running = False
        logger.info("All agents stopped")

    async def send_request(self, agent_name: str, command: str, data: Dict[str, Any] = None, timeout: float = 5.0) -> AgentResponse:
        agent = self._agents.get(agent_name)
        if not agent:
            return AgentResponse(
                request_id=str(uuid.uuid4()),
                agent_name=agent_name,
                status="error",
                error=f"Agent {agent_name} not found",
            )
        return await agent.send_request(command, data, timeout)

    async def send_concurrent(self, requests: Dict[str, tuple], timeout: float = 5.0) -> Dict[str, AgentResponse]:
        tasks = {}
        for agent_name, (command, data) in requests.items():
            agent = self._agents.get(agent_name)
            if agent:
                tasks[agent_name] = asyncio.create_task(
                    agent.send_request(command, data, timeout)
                )

        results = {}
        for agent_name, task in tasks.items():
            try:
                results[agent_name] = await asyncio.wait_for(task, timeout=timeout + 1.0)
            except asyncio.TimeoutError:
                results[agent_name] = AgentResponse(
                    request_id=str(uuid.uuid4()),
                    agent_name=agent_name,
                    status="timeout",
                    error=f"Request timed out after {timeout}s",
                )
            except Exception as e:
                results[agent_name] = AgentResponse(
                    request_id=str(uuid.uuid4()),
                    agent_name=agent_name,
                    status="error",
                    error=str(e),
                )
        return results

    def get_status(self) -> Dict[str, str]:
        return {name: agent.status.value for name, agent in self._agents.items()}


_agent_manager: Optional[AgentManager] = None


def get_agent_manager() -> AgentManager:
    global _agent_manager
    if _agent_manager is None:
        _agent_manager = AgentManager()
    return _agent_manager