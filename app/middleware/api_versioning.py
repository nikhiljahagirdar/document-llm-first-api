"""
API versioning middleware for managing API versions and deprecation.
Supports version-based routing, deprecation warnings, and graceful version handling.
"""

import time
from typing import Optional, Dict, List
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse
import logging

logger = logging.getLogger(__name__)


class APIVersioningMiddleware(BaseHTTPMiddleware):
    """
    API versioning middleware that handles:
    - Version extraction from headers or URL
    - Version validation and routing
    - Deprecation warnings
    - Sunset headers for deprecated versions
    - Version-specific rate limiting
    """
    
    def __init__(self, app):
        super().__init__(app)
        
        # Supported API versions
        self.supported_versions = ["v1", "v1.0", "v1.0.0"]
        self.current_version = "v1"
        
        # Deprecated versions with sunset dates
        self.deprecated_versions = {
            # "v1": "2024-12-31",  # Example: v1 deprecated on Dec 31, 2024
        }
        
        # Version-specific configurations
        self.version_configs = {
            "v1": {
                "max_requests_per_minute": 1000,
                "features": ["documents", "users", "llm", "billing"],
                "deprecated": False,
                "sunset_date": None
            }
        }
        
        # Endpoint version mapping
        self.endpoint_versions = {
            # Current endpoints are v1 by default
            # Future endpoints can be mapped to specific versions
            # "/api/v2/endpoint": "v2"
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract API version
        version = self._extract_version(request)
        
        # Validate version
        if not self._is_version_supported(version):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": f"Unsupported API version: {version}. Supported versions: {', '.join(self.supported_versions)}"}
            )
        
        # Add version to request state for downstream use
        request.state.api_version = version
        
        # Process request
        response = await call_next(request)
        
        # Add version headers
        self._add_version_headers(response, version)
        
        # Add deprecation warnings if needed
        if self._is_version_deprecated(version):
            self._add_deprecation_headers(response, version)
        
        return response
    
    def _extract_version(self, request: Request) -> str:
        """Extract API version from request headers or URL."""
        # Try Accept-Version header first
        accept_version = request.headers.get("Accept-Version")
        if accept_version:
            return accept_version
        
        # Try API-Version header
        api_version = request.headers.get("API-Version")
        if api_version:
            return api_version
        
        # Try URL path versioning
        path_parts = request.url.path.strip("/").split("/")
        if len(path_parts) >= 2 and path_parts[0] == "api":
            potential_version = path_parts[1]
            if potential_version.startswith("v"):
                return potential_version
        
        # Default to current version
        return self.current_version
    
    def _is_version_supported(self, version: str) -> bool:
        """Check if the requested version is supported."""
        return version in self.supported_versions
    
    def _is_version_deprecated(self, version: str) -> bool:
        """Check if the version is deprecated."""
        return version in self.deprecated_versions
    
    def _add_version_headers(self, response: Response, version: str):
        """Add version-related headers to response."""
        response.headers["API-Version"] = version
        response.headers["API-Supported-Versions"] = ", ".join(self.supported_versions)
        response.headers["API-Current-Version"] = self.current_version
        
        # Add version-specific configuration info
        config = self.version_configs.get(version, {})
        features = config.get("features", [])
        response.headers["API-Available-Features"] = ", ".join(features)
    
    def _add_deprecation_headers(self, response: Response, version: str):
        """Add deprecation-related headers."""
        response.headers["Deprecation"] = "true"
        
        sunset_date = self.deprecated_versions.get(version)
        if sunset_date:
            response.headers["Sunset"] = sunset_date
        
        # Add warning header
        warning_message = f"API version {version} is deprecated"
        if sunset_date:
            warning_message += f" and will be sunset on {sunset_date}"
        warning_message += f". Please migrate to {self.current_version}"
        
        response.headers["Warning"] = f'299 - "{warning_message}"'


class APIAnalyticsMiddleware(BaseHTTPMiddleware):
    """
    Middleware for collecting API analytics and metrics.
    Tracks usage patterns, response times, and error rates.
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.analytics_data = {
            "total_requests": 0,
            "requests_by_endpoint": {},
            "requests_by_version": {},
            "requests_by_status": {},
            "response_times": [],
            "errors": []
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        
        # Collect request data
        method = request.method
        path = request.url.path
        version = getattr(request.state, 'api_version', 'unknown')
        
        # Process request
        response = await call_next(request)
        
        # Calculate response time
        response_time = time.time() - start_time
        
        # Update analytics
        self._update_analytics(method, path, version, response.status_code, response_time)
        
        # Add analytics headers (optional, for debugging)
        response.headers["X-Response-Time"] = f"{response_time:.3f}s"
        
        return response
    
    def _update_analytics(self, method: str, path: str, version: str, status_code: int, response_time: float):
        """Update analytics data."""
        self.analytics_data["total_requests"] += 1
        
        # Track by endpoint
        endpoint_key = f"{method} {path}"
        self.analytics_data["requests_by_endpoint"][endpoint_key] = \
            self.analytics_data["requests_by_endpoint"].get(endpoint_key, 0) + 1
        
        # Track by version
        self.analytics_data["requests_by_version"][version] = \
            self.analytics_data["requests_by_version"].get(version, 0) + 1
        
        # Track by status code
        self.analytics_data["requests_by_status"][status_code] = \
            self.analytics_data["requests_by_status"].get(status_code, 0) + 1
        
        # Track response times (keep only last 1000 for memory)
        self.analytics_data["response_times"].append(response_time)
        if len(self.analytics_data["response_times"]) > 1000:
            self.analytics_data["response_times"] = self.analytics_data["response_times"][-1000:]
        
        # Track errors
        if status_code >= 400:
            self.analytics_data["errors"].append({
                "timestamp": time.time(),
                "status_code": status_code,
                "endpoint": f"{method} {path}",
                "version": version
            })
    
    def get_analytics_summary(self) -> Dict:
        """Get a summary of analytics data."""
        total_requests = self.analytics_data["total_requests"]
        if total_requests == 0:
            return {"total_requests": 0}
        
        response_times = self.analytics_data["response_times"]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        return {
            "total_requests": total_requests,
            "average_response_time": round(avg_response_time, 3),
            "requests_by_endpoint": dict(sorted(
                self.analytics_data["requests_by_endpoint"].items(),
                key=lambda x: x[1], reverse=True
            )[:10]),  # Top 10 endpoints
            "requests_by_version": self.analytics_data["requests_by_version"],
            "error_rate": len(self.analytics_data["errors"]) / total_requests,
            "status_distribution": self.analytics_data["requests_by_status"]
        }


class APIValidationMiddleware(BaseHTTPMiddleware):
    """
    Middleware for API request validation and security.
    Validates request headers, content types, and implements security policies.
    """
    
    def __init__(self, app):
        super().__init__(app)
        
        # Allowed content types
        self.allowed_content_types = {
            "GET": [],
            "POST": ["application/json", "multipart/form-data", "application/x-www-form-urlencoded"],
            "PUT": ["application/json", "multipart/form-data"],
            "PATCH": ["application/json"],
            "DELETE": []
        }
        
        # Required headers for sensitive operations
        self.required_headers = {
            "/api/users/login": [],      # Public
            "/api/users/register": [],   # Public
            "/api/plans": [],            # Public
            "/api/billing/checkout": [], # Public
            "/api/documents/upload": ["Content-Type"],
            "/api/llm/generate": ["Content-Type"],
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        method = request.method
        path = request.url.path
        
        # Only validate API endpoints
        if path.startswith("/api/"):
            try:
                # Validate content type
                self._validate_content_type(request, method, path)
                
                # Validate required headers
                self._validate_required_headers(request, path)
            except HTTPException as exc:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail}
                )
        
        # Add security headers
        response = await call_next(request)
        self._add_security_headers(response)
        
        return response
    
    def _validate_content_type(self, request: Request, method: str, path: str):
        """Validate request content type."""
        if method in ["GET", "DELETE"]:
            return  # These methods don't typically have bodies
        
        content_type = request.headers.get("Content-Type", "")
        if not content_type:
            return  # Allow empty/missing Content-Type (standard for empty body POSTs)
        
        allowed_types = self.allowed_content_types.get(method, [])
        
        if allowed_types and not any(allowed in content_type for allowed in allowed_types):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported Media Type. Allowed types: {', '.join(allowed_types)}"
            )
    
    def _validate_required_headers(self, request: Request, path: str):
        """Validate required headers for specific endpoints."""
        required = self.required_headers.get(path, [])
        
        for header in required:
            if header not in request.headers:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Required header missing: {header}"
                )
    
    def _add_security_headers(self, response: Response):
        """Add security-related headers."""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
