"""
API versioning middleware with deprecation support
"""
from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware


class APIVersionMiddleware(BaseHTTPMiddleware):
    """
    Middleware for API versioning and deprecation warnings
    """

    def __init__(self, app):
        super().__init__(app)

        # Version configuration
        self.current_version = "v1"
        self.supported_versions = {"v1"}
        self.deprecated_versions = set()  # Add versions here when deprecating

        # Deprecation warnings
        self.deprecation_messages = {
            # Example: "v0": "API v0 is deprecated and will be removed in 2025-03-01"
        }

    async def dispatch(self, request: Request, call_next):
        """Process request with version checking"""

        # Extract version from path or header
        api_version = self._get_api_version(request)

        # Add version to request state
        request.state.api_version = api_version

        # Check if version is supported
        if api_version and api_version not in self.supported_versions:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=400,
                content={
                    "error": "unsupported_api_version",
                    "message": f"API version '{api_version}' is not supported",
                    "supported_versions": list(self.supported_versions)
                }
            )

        # Process request
        response = await call_next(request)

        # Add version headers
        response.headers["X-API-Version"] = api_version or self.current_version

        # Add deprecation warning if applicable
        if api_version in self.deprecated_versions:
            deprecation_msg = self.deprecation_messages.get(
                api_version,
                f"API {api_version} is deprecated"
            )
            response.headers["X-API-Deprecation"] = deprecation_msg
            response.headers["Warning"] = f'299 - "{deprecation_msg}"'

            logger.warning(
                f"Deprecated API version used: {api_version} on {request.url.path}"
            )

        return response

    def _get_api_version(self, request: Request) -> str:
        """
        Extract API version from request
        
        Priority:
        1. X-API-Version header
        2. Accept header with version
        3. Path prefix (/api/v1/...)
        4. Default to current version
        """
        # Check header first
        version_header = request.headers.get("X-API-Version")
        if version_header:
            return version_header

        # Check Accept header
        accept = request.headers.get("Accept", "")
        if "version=" in accept:
            # Extract version from Accept: application/json; version=v1
            try:
                version_part = [p for p in accept.split(";") if "version=" in p][0]
                return version_part.split("=")[1].strip()
            except (IndexError, AttributeError):
                pass

        # Extract from path
        path_parts = request.url.path.split("/")
        if len(path_parts) >= 3 and path_parts[1] == "api":
            potential_version = path_parts[2]
            if potential_version.startswith("v") and potential_version[1:].isdigit():
                return potential_version

        # Default to current version
        return self.current_version
