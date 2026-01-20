"""Health service for SVTVision."""

from enum import Enum
from typing import Dict, Any
from datetime import datetime, timedelta


class HealthStatus(Enum):
    """Health status enumeration."""
    OK = "OK"
    WARN = "WARN"
    STALE = "STALE"
    ERROR = "ERROR"


class HealthService:
    """Service for managing system health status."""
    
    def __init__(self):
        self.global_health = HealthStatus.OK
        self.component_health: Dict[str, HealthStatus] = {}
        self.last_update: Dict[str, datetime] = {}
        self.reasons: Dict[str, str] = {}
    
    def set_component_health(
        self, 
        component: str, 
        status: HealthStatus, 
        reason: str = ""
    ):
        """Set health status for a component."""
        self.component_health[component] = status
        self.last_update[component] = datetime.now()
        if reason:
            self.reasons[component] = reason
        self._update_global_health()
    
    def get_component_health(self, component: str) -> HealthStatus:
        """Get health status for a component."""
        return self.component_health.get(component, HealthStatus.OK)
    
    def get_component_reason(self, component: str) -> str:
        """Get reason for component health status."""
        return self.reasons.get(component, "")
    
    def _update_global_health(self):
        """Update global health based on component health."""
        if not self.component_health:
            self.global_health = HealthStatus.OK
            return
        
        # Determine worst status
        if any(s == HealthStatus.ERROR for s in self.component_health.values()):
            self.global_health = HealthStatus.ERROR
        elif any(s == HealthStatus.STALE for s in self.component_health.values()):
            self.global_health = HealthStatus.STALE
        elif any(s == HealthStatus.WARN for s in self.component_health.values()):
            self.global_health = HealthStatus.WARN
        else:
            self.global_health = HealthStatus.OK
    
    def get_global_health(self) -> HealthStatus:
        """Get global health status."""
        return self.global_health
    
    def get_all_health(self) -> Dict[str, Any]:
        """Get all health information."""
        return {
            "global": self.global_health.value,
            "components": {
                comp: {
                    "status": status.value,
                    "reason": self.reasons.get(comp, ""),
                    "last_update": self.last_update.get(comp).isoformat() if comp in self.last_update else None
                }
                for comp, status in self.component_health.items()
            }
        }
