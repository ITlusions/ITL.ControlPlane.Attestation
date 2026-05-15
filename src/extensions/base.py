"""
Base class for attestation platform extensions.

Extensions must subclass AttestationExtension and implement all abstract methods.
Extensions are discovered automatically via extensions/__init__.py discovery mechanism.
"""

from abc import ABC, abstractmethod
from typing import Optional
from fastapi import APIRouter


class AttestationExtension(ABC):
    """
    Base class for attestation platform extensions.
    
    Extensions provide modular functionality on top of the core attestation service.
    Each extension can contribute:
    - REST API routes (via get_router)
    - Database models (via get_models)
    - Lifecycle hooks (on_startup, on_shutdown)
    
    Example:
        class MyExtension(AttestationExtension):
            @property
            def name(self) -> str:
                return "my_extension"
            
            @property
            def version(self) -> str:
                return "1.0.0"
            
            @property
            def description(self) -> str:
                return "My custom extension"
            
            def get_router(self) -> Optional[APIRouter]:
                router = APIRouter(prefix="/api/v1/my", tags=["my"])
                
                @router.get("/hello")
                async def hello():
                    return {"message": "Hello from my extension"}
                
                return router
            
            def get_models(self) -> list[type]:
                return []  # No custom models
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        Extension identifier (snake_case).
        
        Must be unique across all extensions.
        Used for:
        - Extension registry key
        - CLI subcommand prefix
        - Database table prefix (extension_<name>_*)
        
        Returns:
            Extension name in snake_case (e.g., "secret_vault")
        """
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        """
        Semantic version string.
        
        Returns:
            Version in semver format (e.g., "1.0.0")
        """
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """
        Human-readable description of extension functionality.
        
        Returns:
            Single-line description
        """
        pass
    
    @abstractmethod
    def get_router(self) -> Optional[APIRouter]:
        """
        Return FastAPI router for this extension's REST endpoints.
        
        The router should use a unique prefix (e.g., /api/v1/secrets).
        All routes will be automatically registered in the attestation service.
        
        Returns:
            APIRouter instance or None if extension has no REST endpoints
        """
        pass
    
    @abstractmethod
    def get_models(self) -> list[type]:
        """
        Return SQLModel classes for database migrations.
        
        Models will be automatically discovered by Alembic for migration generation.
        Table names should use prefix: extension_<name>_*
        
        Returns:
            List of SQLModel classes or empty list if no models
        """
        pass
    
    def on_startup(self) -> None:
        """
        Lifecycle hook called when the attestation service starts.
        
        Override to perform initialization tasks such as:
        - Validate configuration
        - Establish external connections
        - Start background tasks
        
        Default implementation does nothing.
        """
        pass
    
    def on_shutdown(self) -> None:
        """
        Lifecycle hook called when the attestation service stops.
        
        Override to perform cleanup tasks such as:
        - Close connections
        - Stop background tasks
        - Flush buffers
        
        Default implementation does nothing.
        """
        pass
