"""
Centralized hardware health monitoring system.

Provides rate-limited error logging, expected error suppression,
and degradation detection for all hardware components.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Optional, List
import time
import threading

from utils.logger import log_error, log


class ComponentStatus(Enum):
    """Health status of a hardware component"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"          # Intermittent errors occurring
    FAILED = "failed"              # Persistent failure, component disabled
    NOT_AVAILABLE = "not_available"  # Hardware not present/initialized


@dataclass
class ComponentHealth:
    """Current health state of a component (for API responses)"""
    name: str
    status: ComponentStatus
    last_error: Optional[str] = None
    error_count: int = 0
    last_success: Optional[float] = None


class ComponentTracker:
    """
    Tracks health for a single hardware component.
    Handles error throttling, expected error suppression, and degradation detection.
    """
    
    def __init__(
        self,
        name: str,
        expected_errors: Optional[List[str]] = None,
        log_interval: float = 5.0,
        failure_threshold: int = 20,
        degraded_threshold: int = 3
    ):
        """
        Initialize component tracker.
        
        Args:
            name: Component identifier (e.g., "buttons", "nfc")
            expected_errors: List of error substrings to suppress completely
            log_interval: Minimum seconds between logged errors
            failure_threshold: Consecutive errors before marking as failed
            degraded_threshold: Consecutive errors before marking as degraded
        """
        self.name = name
        self._expected_errors = expected_errors or []
        self._log_interval = log_interval
        self._failure_threshold = failure_threshold
        self._degraded_threshold = degraded_threshold
        
        # State tracking
        self._status = ComponentStatus.HEALTHY
        self._consecutive_errors = 0
        self._total_errors = 0
        self._last_error: Optional[str] = None
        self._last_error_log_time = 0.0
        self._last_success_time: Optional[float] = None
        self._failed_logged = False  # Track if we've logged the failure message
        
        self._lock = threading.Lock()
    
    def _is_expected_error(self, error: Exception) -> bool:
        """Check if error matches any expected error patterns"""
        error_msg = str(error)
        return any(expected in error_msg for expected in self._expected_errors)
    
    def report_success(self):
        """
        Report a successful operation.
        Resets error state and marks component as healthy.
        """
        with self._lock:
            self._consecutive_errors = 0
            self._last_success_time = time.time()
            self._failed_logged = False
            
            # Only transition back to healthy if we were degraded
            # Failed components stay failed until explicitly reset
            if self._status == ComponentStatus.DEGRADED:
                self._status = ComponentStatus.HEALTHY
                log(f"Hardware '{self.name}' recovered to healthy state", "HEALTH")
    
    def report_error(self, error: Exception) -> bool:
        """
        Report an error occurrence.
        
        Args:
            error: The exception that occurred
            
        Returns:
            True if the error should be logged (not suppressed/throttled)
        """
        with self._lock:
            self._consecutive_errors += 1
            self._total_errors += 1
            self._last_error = str(error)
            
            # Update status based on consecutive errors
            if self._consecutive_errors >= self._failure_threshold:
                if self._status != ComponentStatus.FAILED:
                    self._status = ComponentStatus.FAILED
            elif self._consecutive_errors >= self._degraded_threshold:
                if self._status == ComponentStatus.HEALTHY:
                    self._status = ComponentStatus.DEGRADED
            
            # Check if this is an expected error (suppress completely)
            if self._is_expected_error(error):
                return False
            
            # Rate-limit logging
            current_time = time.time()
            if current_time - self._last_error_log_time < self._log_interval:
                return False
            
            self._last_error_log_time = current_time
            return True
    
    def is_failed(self) -> bool:
        """Check if component is in failed state"""
        with self._lock:
            return self._status == ComponentStatus.FAILED
    
    def is_degraded(self) -> bool:
        """Check if component is degraded or failed"""
        with self._lock:
            return self._status in (ComponentStatus.DEGRADED, ComponentStatus.FAILED)
    
    def log_failure_once(self, message: str):
        """
        Log a failure message only once (until component recovers).
        Use this for "component disabled" type messages.
        """
        with self._lock:
            if not self._failed_logged:
                self._failed_logged = True
                log_error(message)
    
    def get_health(self) -> ComponentHealth:
        """Get current health state"""
        with self._lock:
            return ComponentHealth(
                name=self.name,
                status=self._status,
                last_error=self._last_error,
                error_count=self._total_errors,
                last_success=self._last_success_time
            )
    
    def reset(self):
        """
        Force reset component to healthy state.
        Use for manual recovery attempts.
        """
        with self._lock:
            self._status = ComponentStatus.HEALTHY
            self._consecutive_errors = 0
            self._failed_logged = False
            log(f"Hardware '{self.name}' manually reset to healthy state", "HEALTH")


class HardwareHealthManager:
    """
    Singleton manager for all hardware component health.
    
    Usage:
        manager = HardwareHealthManager.get_instance()
        tracker = manager.register("buttons", expected_errors=["I/O error"])
        
        # In component code:
        try:
            result = do_hardware_operation()
            tracker.report_success()
        except Exception as e:
            if tracker.report_error(e):
                log_error(f"Button error: {e}")
            if tracker.is_failed():
                tracker.log_failure_once("Buttons disabled due to repeated errors")
    """
    
    _instance: Optional["HardwareHealthManager"] = None
    _lock = threading.Lock()
    
    def __init__(self):
        """Initialize the health manager"""
        self._components: Dict[str, ComponentTracker] = {}
        self._components_lock = threading.Lock()
    
    @classmethod
    def get_instance(cls) -> "HardwareHealthManager":
        """Get the singleton instance"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
    
    def register(
        self,
        name: str,
        expected_errors: Optional[List[str]] = None,
        log_interval: float = 5.0,
        failure_threshold: int = 20,
        degraded_threshold: int = 3
    ) -> ComponentTracker:
        """
        Register a hardware component for health tracking.
        
        Args:
            name: Unique component identifier
            expected_errors: Error substrings to suppress (e.g., ["Input/output error"])
            log_interval: Minimum seconds between logged errors (default 5.0)
            failure_threshold: Consecutive errors before marking failed (default 20)
            degraded_threshold: Consecutive errors before marking degraded (default 3)
            
        Returns:
            ComponentTracker instance for the component
        """
        with self._components_lock:
            if name in self._components:
                # Return existing tracker if already registered
                return self._components[name]
            
            tracker = ComponentTracker(
                name=name,
                expected_errors=expected_errors,
                log_interval=log_interval,
                failure_threshold=failure_threshold,
                degraded_threshold=degraded_threshold
            )
            self._components[name] = tracker
            return tracker
    
    def get_tracker(self, name: str) -> Optional[ComponentTracker]:
        """Get tracker for a component by name"""
        with self._components_lock:
            return self._components.get(name)
    
    def get_status(self, name: str) -> Optional[ComponentHealth]:
        """Get health status of a specific component"""
        tracker = self.get_tracker(name)
        if tracker:
            return tracker.get_health()
        return None
    
    def get_all_status(self) -> Dict[str, ComponentHealth]:
        """Get health status of all registered components"""
        with self._components_lock:
            return {
                name: tracker.get_health()
                for name, tracker in self._components.items()
            }
    
    def reset_component(self, name: str) -> bool:
        """
        Reset a component to healthy state.
        
        Returns:
            True if component was found and reset, False otherwise
        """
        tracker = self.get_tracker(name)
        if tracker:
            tracker.reset()
            return True
        return False
    
    def reset_all(self):
        """Reset all components to healthy state"""
        with self._components_lock:
            for tracker in self._components.values():
                tracker.reset()
