"""File coordination - locks and conflict detection."""

from dataclasses import dataclass

import redis.asyncio as redis
import structlog

from src.orchestrator.config import Settings

logger = structlog.get_logger()


@dataclass
class LockResult:
    """Result of a lock acquisition attempt."""
    acquired: bool
    conflicting_task: str | None = None
    conflicting_file: str | None = None


class FileCoordinator:
    """Coordinates file access across agents."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.redis: redis.Redis | None = None
    
    async def _get_redis(self) -> redis.Redis:
        """Lazy Redis connection."""
        if self.redis is None:
            self.redis = redis.from_url(self.settings.redis_url)
        return self.redis
    
    def _lock_key(self, repo: str, file_path: str) -> str:
        """Generate Redis key for file lock."""
        return f"lock:{repo}:{file_path}"
    
    async def check_conflicts(
        self,
        repo: str,
        files: set[str],
    ) -> LockResult:
        """Check if any files are locked by another task."""
        r = await self._get_redis()
        
        for file_path in files:
            key = self._lock_key(repo, file_path)
            holder = await r.get(key)
            
            if holder:
                holder_str = holder.decode() if isinstance(holder, bytes) else holder
                return LockResult(
                    acquired=False,
                    conflicting_task=holder_str,
                    conflicting_file=file_path,
                )
        
        return LockResult(acquired=True)
    
    async def acquire_locks(
        self,
        task_id: str,
        repo: str,
        files: set[str],
        ttl: int | None = None,
    ) -> LockResult:
        """Acquire locks on a set of files."""
        if ttl is None:
            ttl = self.settings.file_lock_ttl_seconds
        
        # First check for conflicts
        conflict = await self.check_conflicts(repo, files)
        if not conflict.acquired:
            return conflict
        
        # Acquire all locks atomically
        r = await self._get_redis()
        pipe = r.pipeline()
        
        for file_path in files:
            key = self._lock_key(repo, file_path)
            pipe.setex(key, ttl, task_id)
        
        await pipe.execute()
        
        logger.info(
            "Acquired file locks",
            task_id=task_id,
            repo=repo,
            file_count=len(files),
        )
        
        return LockResult(acquired=True)
    
    async def release_locks(
        self,
        task_id: str,
        repo: str,
    ) -> int:
        """Release all locks held by a task."""
        r = await self._get_redis()
        
        # Find all locks for this repo
        pattern = self._lock_key(repo, "*")
        released = 0
        
        async for key in r.scan_iter(match=pattern):
            holder = await r.get(key)
            if holder:
                holder_str = holder.decode() if isinstance(holder, bytes) else holder
                if holder_str == task_id:
                    await r.delete(key)
                    released += 1
        
        if released > 0:
            logger.info(
                "Released file locks",
                task_id=task_id,
                repo=repo,
                count=released,
            )
        
        return released
    
    async def extend_locks(
        self,
        task_id: str,
        repo: str,
        ttl: int | None = None,
    ) -> int:
        """Extend TTL on all locks held by a task."""
        if ttl is None:
            ttl = self.settings.file_lock_ttl_seconds
        
        r = await self._get_redis()
        pattern = self._lock_key(repo, "*")
        extended = 0
        
        async for key in r.scan_iter(match=pattern):
            holder = await r.get(key)
            if holder:
                holder_str = holder.decode() if isinstance(holder, bytes) else holder
                if holder_str == task_id:
                    await r.expire(key, ttl)
                    extended += 1
        
        return extended
    
    async def get_locked_files(self, repo: str) -> dict[str, str]:
        """Get all locked files in a repo with their holders."""
        r = await self._get_redis()
        pattern = self._lock_key(repo, "*")
        
        locks = {}
        prefix_len = len(self._lock_key(repo, ""))
        
        async for key in r.scan_iter(match=pattern):
            key_str = key.decode() if isinstance(key, bytes) else key
            file_path = key_str[prefix_len:]
            
            holder = await r.get(key)
            if holder:
                holder_str = holder.decode() if isinstance(holder, bytes) else holder
                locks[file_path] = holder_str
        
        return locks
