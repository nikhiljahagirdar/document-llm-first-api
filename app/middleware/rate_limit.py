"""
Rate limiting middleware for API endpoints.
Provides configurable rate limiting based on user roles and subscription tiers.
"""

import time
import asyncio
from typing import Dict, Optional
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import redis.asyncio as aioredis
from app.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using Redis for distributed rate limiting.
    
    Features:
    - Different limits per user role/subscription tier
    - Sliding window implementation
    - Redis-based for distributed systems
    - Configurable endpoints with custom limits
    """
    
    def __init__(self, app, redis_client: Optional[aioredis.Redis] = None):
        super().__init__(app)
        self.redis_client = redis_client
        self.limits = {
            # Default limits (requests per minute)
            "default": 60,
            "free": 30,
            "basic": 100,
            "pro": 500,
            "enterprise": 2000,
            # Special endpoints with stricter limits
            "auth": 10,  # Login/register attempts
            "upload": 20,  # File uploads
            "llm": 50,    # LLM processing requests
        }
        
        # Endpoint categories
        self.endpoint_categories = {
            "/api/users/login": "auth",
            "/api/users/register": "auth",
            "/api/documents/upload": "upload",
            "/api/llm/": "llm",
            "/api/llm/chat": "llm",
            "/api/llm/generate": "llm",
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for health checks and docs
        if self._should_skip_rate_limit(request):
            return await call_next(request)
        
        # Get client identifier
        client_id = await self._get_client_id(request)
        
        # Determine rate limit based on user tier and endpoint
        limit = await self._get_rate_limit(request, client_id)
        
        # Check rate limit
        if not await self._check_rate_limit(client_id, limit, request.url.path):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={
                    "Retry-After": str(60),  # Suggest retry after 1 minute
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + 60))
                }
            )
        
        # Add rate limit headers
        response = await call_next(request)
        remaining = await self._get_remaining_requests(client_id, limit)
        
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time() + 60))
        
        return response
    
    def _should_skip_rate_limit(self, request: Request) -> bool:
        """Skip rate limiting for certain endpoints."""
        skip_paths = [
            "/",
            "/docs",
            "/redoc", 
            "/openapi.json",
            "/health",
            "/metrics"
        ]
        return request.url.path in skip_paths
    
    async def _get_client_id(self, request: Request) -> str:
        """Get client identifier for rate limiting."""
        # Try to get user ID from token
        if hasattr(request.state, 'user_id'):
            return f"user:{request.state.user_id}"
        
        # Fall back to IP address
        client_ip = request.client.host
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        
        return f"ip:{client_ip}"
    
    async def _get_rate_limit(self, request: Request, client_id: str) -> int:
        """Determine rate limit based on user tier and endpoint."""
        # Check endpoint-specific limits first
        endpoint_path = request.url.path
        for endpoint, category in self.endpoint_categories.items():
            if endpoint_path.startswith(endpoint):
                return self.limits.get(category, self.limits["default"])
        
        # Try to get user tier from request state (set by auth middleware)
        if hasattr(request.state, 'user_tier'):
            tier = request.state.user_tier
            return self.limits.get(tier, self.limits["default"])
        
        # Default limit
        return self.limits["default"]
    
    async def _check_rate_limit(self, client_id: str, limit: int, path: str) -> bool:
        """Check if client has exceeded rate limit."""
        if not self.redis_client:
            # If no Redis, allow all requests (dev environment)
            return True
        
        current_time = int(time.time())
        window_start = current_time - 60  # 1-minute sliding window
        
        # Use Redis sorted set for sliding window
        key = f"rate_limit:{client_id}:{path}"
        
        try:
            # Remove old entries outside the window
            await self.redis_client.zremrangebyscore(key, 0, window_start)
            
            # Count current requests
            current_requests = await self.redis_client.zcard(key)
            
            if current_requests >= limit:
                return False
            
            # Add current request
            await self.redis_client.zadd(key, {str(current_time): current_time})
            await self.redis_client.expire(key, 60)  # Auto-expire after 1 minute
            
            return True
            
        except Exception:
            # If Redis fails, allow the request (fail open)
            return True
    
    async def _get_remaining_requests(self, client_id: str, limit: int) -> int:
        """Get remaining requests for the client."""
        if not self.redis_client:
            return limit
        
        try:
            current_time = int(time.time())
            window_start = current_time - 60
            key = f"rate_limit:{client_id}:*"
            
            # Count all requests for this client in the current window
            keys = await self.redis_client.keys(key)
            total_requests = 0
            
            for k in keys:
                await self.redis_client.zremrangebyscore(k, 0, window_start)
                total_requests += await self.redis_client.zcard(k)
            
            remaining = max(0, limit - total_requests)
            return remaining
            
        except Exception:
            return limit


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    """
    In-memory rate limiting middleware for development environments.
    Uses a simple dictionary-based approach.
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.requests: Dict[str, list] = {}
        self.limits = {
            "default": 1000,  # Generous limit for development
            "auth": 100,
            "upload": 100,
            "llm": 200,
        }
        
        self.endpoint_categories = {
            "/api/users/login": "auth",
            "/api/users/register": "auth",
            "/api/documents/upload": "upload",
            "/api/llm/": "llm",
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        if self._should_skip_rate_limit(request):
            return await call_next(request)
        
        client_id = await self._get_client_id(request)
        limit = self._get_rate_limit(request)
        
        if not self._check_rate_limit(client_id, limit, request.url.path):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": "60"}
            )
        
        return await call_next(request)
    
    def _should_skip_rate_limit(self, request: Request) -> bool:
        skip_paths = ["/", "/docs", "/redoc", "/openapi.json", "/health"]
        return request.url.path in skip_paths
    
    async def _get_client_id(self, request: Request) -> str:
        if hasattr(request.state, 'user_id'):
            return f"user:{request.state.user_id}"
        
        client_ip = request.client.host
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        
        return f"ip:{client_ip}"
    
    def _get_rate_limit(self, request: Request) -> int:
        endpoint_path = request.url.path
        for endpoint, category in self.endpoint_categories.items():
            if endpoint_path.startswith(endpoint):
                return self.limits.get(category, self.limits["default"])
        
        return self.limits["default"]
    
    def _check_rate_limit(self, client_id: str, limit: int, path: str) -> bool:
        current_time = time.time()
        window_start = current_time - 60
        
        # Clean old entries
        if client_id in self.requests:
            self.requests[client_id] = [
                req_time for req_time in self.requests[client_id]
                if req_time > window_start
            ]
        else:
            self.requests[client_id] = []
        
        # Check limit
        if len(self.requests[client_id]) >= limit:
            return False
        
        # Add current request
        self.requests[client_id].append(current_time)
        return True
