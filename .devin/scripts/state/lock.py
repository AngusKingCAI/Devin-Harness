"""Orchestrator lock implementation for process synchronization."""

import logging
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# Setup logging for this module
def setup_logging(module_name: str):
    """Setup JSONL logging for a module."""
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"{module_name}-Log.jsonl"
    
    class JsonFormatter(logging.Formatter):
        def format(self, record):
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "level": record.levelname,
                "module": record.name,
                "function": record.funcName,
                "line": record.lineno,
                "message": record.getMessage(),
            }
            
            if record.exc_info:
                log_entry["exception"] = self.formatException(record.exc_info)
            
            if hasattr(record, 'extra_fields'):
                log_entry.update(record.extra_fields)
            
            return json.dumps(log_entry)
    
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JsonFormatter())
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s:%(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    logger = logging.getLogger(module_name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging(__name__)


class OrchestratorLock:
    """File-based lock for orchestrator process synchronization."""
    
    def __init__(self, lock_path: Path):
        """
        Initialize lock with a specific file path.
        
        Args:
            lock_path: Path to the lock file
        """
        self.lock_path = lock_path
        self.lock_file = None
        logger.info(f"Initialized OrchestratorLock with path: {lock_path}")
    
    def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire the lock.
        
        Args:
            timeout: Maximum time to wait for lock (None = wait indefinitely)
            
        Returns:
            True if lock acquired, False otherwise
        """
        logger.info(f"Attempting to acquire lock: {self.lock_path}")
        
        try:
            # Open the lock file in exclusive mode
            self.lock_file = open(self.lock_path, 'w')
            
            # Try to acquire exclusive lock
            if sys.platform == 'win32':
                # Windows: use msvcrt.locking or fallback to simple file check
                return self._acquire_windows(timeout)
            else:
                # POSIX: use fcntl.flock
                return self._acquire_posix(timeout)
                
        except Exception as e:
            logger.error(f"Failed to acquire lock: {e}", exc_info=True)
            if self.lock_file:
                self.lock_file.close()
                self.lock_file = None
            return False
    
    def _acquire_posix(self, timeout: Optional[float]) -> bool:
        """Acquire lock using fcntl on POSIX systems."""
        import fcntl
        
        if timeout is not None:
            # Non-blocking mode with timeout
            import time
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    logger.info("Lock acquired (POSIX)")
                    return True
                except (IOError, BlockingIOError):
                    time.sleep(0.1)
            
            logger.warning(f"Failed to acquire lock within timeout {timeout}s")
            return False
        else:
            # Blocking mode
            try:
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX)
                logger.info("Lock acquired (POSIX)")
                return True
            except Exception as e:
                logger.error(f"Failed to acquire lock: {e}", exc_info=True)
                return False
    
    def _acquire_windows(self, timeout: Optional[float]) -> bool:
        """Acquire lock on Windows using msvcrt locking."""
        try:
            import msvcrt
            msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            logger.info("Lock acquired (Windows)")
            return True
        except (ImportError, IOError):
            # Fallback to simple file-based lock
            return self._acquire_windows_fallback(timeout)
    
    def _acquire_windows_fallback(self, timeout: Optional[float]) -> bool:
        """Fallback lock implementation for Windows without msvcrt."""
        import time
        
        if timeout is not None:
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    # Try to create the lock file exclusively
                    fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    os.close(fd)
                    logger.info("Lock acquired (Windows fallback)")
                    return True
                except FileExistsError:
                    time.sleep(0.1)
            
            logger.warning(f"Failed to acquire lock within timeout {timeout}s")
            return False
        else:
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                logger.info("Lock acquired (Windows fallback)")
                return True
            except FileExistsError as e:
                logger.error(f"Failed to acquire lock: {e}")
                return False
    
    def release(self) -> None:
        """Release the lock."""
        logger.info(f"Releasing lock: {self.lock_path}")
        
        if self.lock_file:
            try:
                if sys.platform == 'win32':
                    # Windows: close the file (releases lock)
                    pass
                else:
                    # POSIX: release the flock
                    import fcntl
                    fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                
                self.lock_file.close()
                self.lock_file = None
                
                # Remove the lock file
                if self.lock_path.exists():
                    self.lock_path.unlink()
                    
                logger.info("Lock released successfully")
                
            except Exception as e:
                logger.error(f"Failed to release lock: {e}", exc_info=True)
    
    def __enter__(self):
        """Context manager entry."""
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()