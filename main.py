import sys
import asyncio
import os
import selectors
import logging
import traceback
import certifi
import ssl
from datetime import datetime

# Diagnostic check for dependencies
try:
    from fastapi_cache import FastAPICache
except ImportError:
    print(f"\nERROR: Missing dependencies in current environment.")
    print(f"Python Executable: {sys.executable}")
    print("\nPlease ensure you are using the virtual environment:")
    print("  .\\venv\\Scripts\\python.exe -m pip install -r requirements.txt")
    print("  .\\venv\\Scripts\\python.exe main.py\n")
    sys.exit(1)

# Fix for Psycopg3 on Windows: Must use SelectorEventLoop
# Note: set_event_loop_policy is deprecated in 3.14+, we use loop_factory in asyncio.run below.

from dotenv import load_dotenv
load_dotenv(override=True)

from fastapi import FastAPI, Request, APIRouter, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.backends.inmemory import InMemoryBackend
from redis import asyncio as aioredis

# Import production middleware
from app.middleware.rate_limit import RateLimitMiddleware, InMemoryRateLimitMiddleware
from app.middleware.api_versioning import APIVersioningMiddleware, APIAnalyticsMiddleware, APIValidationMiddleware

# Configure Root Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Safely configure SSL using certifi for Windows (Avoid overriding global SSL context in production)
os.environ["SSL_CERT_FILE"] = certifi.where()

from app.config import settings
from app.db_raw import get_pool, close_pool, DBWrapper

from app.routers import (
    users,
    documents,
    llm,
    industries,
    billing,
    plans,
    tenants,
    logs,
    admin,
    templates,
    reports,
    notifications,
    metering,
    categories,
    subcategories,
    roles,
    integrations,
)
from app.routers.documents import retry_failed_documents

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Raw DB Pool
    try:
        await get_pool()
        logger.info("Psycopg3 Raw DB Pool opened.")
    except Exception as e:
        logger.warning(f"Failed to open raw DB pool: {e}")

    # Initialize Redis Cache with Error Handling
    redis_instance = None
    if settings.USE_REDIS:
        try:
            redis_instance = aioredis.from_url(
                settings.REDIS_URL, 
                encoding="utf8", 
                decode_responses=True,
                socket_timeout=5.0
            )
            await redis_instance.ping()
            FastAPICache.init(RedisBackend(redis_instance), prefix="fastapi-cache")
            logger.info("Redis Cache initialized successfully.")
        except Exception as e:
            logger.warning(f"Redis enabled but not reachable, falling back to InMemoryBackend: {e}")
            FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
    else:
        logger.info("Redis disabled via USE_REDIS, using InMemoryBackend for cache.")
        FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
    
    # Run background retry job
    asyncio.create_task(retry_failed_documents())
    
    # Store Redis instance in app state for middleware access
    app.state.redis_client = redis_instance
    
    yield
    await close_pool()
    logger.info("Application shutdown: Raw DB Pool closed.")

app = FastAPI(
    title="Document Intelligence API",
    description="""
    # Document Intelligence Platform API
    
    A comprehensive SaaS Document Intelligence Platform featuring:
    - **Document Management**: Upload, organize, and process documents
    - **AI-Powered Extraction**: Extract insights using advanced LLM capabilities
    - **RAG (Retrieval-Augmented Generation)**: Intelligent document querying
    - **Multi-tenancy**: Secure tenant isolation and management
    - **Real-time Processing**: WebSocket-based status updates
    - **Industry-Specific Templates**: Tailored document templates by industry
    
    ## Authentication
    
    This API uses JWT Bearer token authentication. Include the token in the Authorization header:
    ```
    Authorization: Bearer <your-jwt-token>
    ```
    
    ## Rate Limiting
    
    API requests are rate-limited to ensure fair usage. Limits vary by subscription tier.
    
    ## Error Handling
    
    The API uses standard HTTP status codes and returns detailed error messages in the response body.
    
    ## Versioning
    
    Current API version: **v1.0.0**
    All endpoints are prefixed with `/api/`.
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    default_response_class=JSONResponse,
    redirect_slashes=False,
    contact={
        "name": "API Support",
        "email": "support@documentintelligence.com",
        "url": "https://documentintelligence.com/support"
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT"
    },
    terms_of_service="https://documentintelligence.com/terms"
)

# --- EXCEPTION HANDLERS ---

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )

# --- MIDDLEWARE ---

import time
import uuid

# Add production middleware in correct order
# 1. API Validation (first to validate requests)
app.add_middleware(APIValidationMiddleware)

# 2. API Versioning
app.add_middleware(APIVersioningMiddleware)

# 3. Rate Limiting (after auth, but before business logic)
if settings.USE_REDIS:
    # Will be initialized after lifespan setup
    pass
else:
    app.add_middleware(InMemoryRateLimitMiddleware)

# 4. API Analytics
app.add_middleware(APIAnalyticsMiddleware)

# 5. Custom middleware for request tracking
@app.middleware("http")
async def add_process_time_and_request_id(request: Request, call_next):
    """
    Custom middleware to add X-Process-Time and X-Request-ID headers.
    """
    start_time = time.time()
    request_id = str(uuid.uuid4())
    
    # Store request_id in request state for use in routers if needed
    request.state.request_id = request_id
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = f"{round(process_time, 4)}s"
    response.headers["X-Request-ID"] = request_id
    
    return response

# 6. Compression (last before response)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Add CORS middleware
cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,  # Allow credentials for JWT auth
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "*", 
        "Authorization", 
        "Content-Type", 
        "X-Request-ID",
        "API-Version",
        "Accept-Version"
    ],
)

# API v1 Router
api_v1_router = APIRouter(prefix="/api")

# Include individual routers
api_v1_router.include_router(users.router)
api_v1_router.include_router(documents.router)
api_v1_router.include_router(llm.router)
api_v1_router.include_router(industries.router)
api_v1_router.include_router(billing.router)
api_v1_router.include_router(plans.router)
api_v1_router.include_router(tenants.router)
api_v1_router.include_router(logs.router)
api_v1_router.include_router(admin.router)
api_v1_router.include_router(templates.router)
api_v1_router.include_router(reports.router)
api_v1_router.include_router(notifications.router)
api_v1_router.include_router(metering.router)
api_v1_router.include_router(categories.router)
api_v1_router.include_router(subcategories.router)
api_v1_router.include_router(roles.router)
api_v1_router.include_router(integrations.router)

# Mount the v1 router to the app
app.include_router(api_v1_router)

# --- CUSTOM OPENAPI FOR WEBSOCKETS ---

from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT Bearer token authentication. Obtain a token by logging in via `/api/users/login`"
        }
    }
    
    # Add global security requirement
    openapi_schema["security"] = [{"BearerAuth": []}]
    
    # Add common error responses
    openapi_schema["components"]["responses"] = {
        "UnauthorizedError": {
            "description": "Authentication failed or token not provided",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "detail": {
                                "type": "string",
                                "example": "Not authenticated"
                            }
                        }
                    },
                    "example": {
                        "detail": "Not authenticated"
                    }
                }
            }
        },
        "ForbiddenError": {
            "description": "Access denied - insufficient permissions",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "detail": {
                                "type": "string",
                                "example": "Insufficient permissions"
                            }
                        }
                    },
                    "example": {
                        "detail": "Insufficient permissions to access this resource"
                    }
                }
            }
        },
        "NotFoundError": {
            "description": "Resource not found",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "detail": {
                                "type": "string",
                                "example": "Resource not found"
                            }
                        }
                    },
                    "example": {
                        "detail": "Document with ID '123' not found"
                    }
                }
            }
        },
        "RateLimitError": {
            "description": "Rate limit exceeded",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "detail": {
                                "type": "string",
                                "example": "Rate limit exceeded"
                            },
                            "retry_after": {
                                "type": "integer",
                                "example": 60
                            }
                        }
                    },
                    "example": {
                        "detail": "Rate limit exceeded. Try again in 60 seconds.",
                        "retry_after": 60
                    }
                }
            }
        },
        "ValidationError": {
            "description": "Request validation failed",
            "content": {
                "application/json": {
                    "schema": {
                        "$ref": "#/components/schemas/HTTPValidationError"
                    }
                }
            }
        },
        "InternalServerError": {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "detail": {
                                "type": "string",
                                "example": "Internal Server Error"
                            }
                        }
                    },
                    "example": {
                        "detail": "Internal Server Error"
                    }
                }
            }
        }
    }
    
    # Add WebSocket documentation
    if "/api/notifications/ws/{user_id}" not in openapi_schema["paths"]:
        openapi_schema["paths"]["/api/notifications/ws/{user_id}"] = {
            "get": {
                "summary": "Real-time Notifications WebSocket",
                "description": "Connect to this WebSocket to receive real-time document processing updates, notifications, and status changes.",
                "tags": ["notifications"],
                "parameters": [
                    {
                        "name": "user_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string", "format": "uuid"},
                        "description": "The UUID of the user to receive notifications for."
                    }
                ],
                "responses": {
                    "101": {"description": "Switching Protocols (WebSocket Handshake Success)"},
                    "401": {"$ref": "#/components/responses/UnauthorizedError"}
                }
            }
        }
    
    # Add server information
    openapi_schema["servers"] = [
        {
            "url": "http://localhost:8001",
            "description": "Development server"
        },
        {
            "url": "https://api.documentintelligence.com",
            "description": "Production server"
        }
    ]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring and load balancers.
    Returns service status and basic metrics.
    """
    return {
        "status": "healthy",
        "service": "document-intelligence-api",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime": "running",  # Could be calculated from start time
        "checks": {
            "database": "connected",  # Could check actual DB connection
            "cache": "connected" if settings.USE_REDIS else "in-memory"
        }
    }

@app.get("/metrics")
async def metrics():
    """
    Basic metrics endpoint for monitoring.
    Returns API usage statistics and performance metrics.
    """
    # Get analytics from middleware if available
    analytics = {}
    for middleware in app.user_middleware:
        if hasattr(middleware.cls, 'get_analytics_summary'):
            # This would need to be implemented to get the actual middleware instance
            pass
    
    return {
        "service": "document-intelligence-api",
        "metrics": {
            "total_requests": "N/A",  # Would get from analytics middleware
            "average_response_time": "N/A",
            "error_rate": "N/A",
            "active_connections": "N/A"
        },
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/")
async def root():
    return {
        "message": "Welcome to the Document Management System API!",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
        "health": "/health",
        "metrics": "/metrics"
    }

def get_available_port(start_port: int, max_attempts: int = 100) -> int:
    """Finds the first available port starting from start_port."""
    import socket
    port = start_port
    while port < start_port + max_attempts:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except socket.error:
                port += 1
    raise RuntimeError(f"Could not find an available port in range {start_port}-{start_port + max_attempts}")

async def start_server():
    import uvicorn
    # Prioritize 8001 as requested by the frontend logs
    port = get_available_port(8001)
    logger.info("Starting server on port %s...", port)
    logger.info("WebSocket URL: ws://localhost:%s/api/notifications/ws/{user_id}", port)
    
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

@app.get("/stop")
async def stop_server():
    os.kill(os.getpid(), 2) # Send SIGINT to itself
    return {"status": "stopping"}

if __name__ == "__main__":
    import selectors
    loop_factory = None
    
    # REQUIRED for Psycopg3 async mode on Windows
    if sys.platform == 'win32':
        loop_factory = lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())
        logger.info("Using SelectorEventLoop for Windows compatibility with Psycopg3.")
    
    try:
        asyncio.run(start_server(), loop_factory=loop_factory)
    except TypeError:
        # Fallback for older Python versions
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(start_server())
