"""
API versioning middleware with deprecation support
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware


class APIVersionMiddleware(BaseHTTPMiddleware):
    """
    Middleware for API versioning and deprecation warnings
    """

    def __init__(self, app):
        super().__init__(app)

        self.current_version = "v1"
        self.supported_versions = {"v1"}
        self.deprecated_versions = set()

        self.deprecation_messages = {}

    async def dispatch(self, request: Request, call_next):
        """Process request with version checking"""

        api_version = self._get_api_version(request)

        request.state.api_version = api_version

        if api_version and api_version not in self.supported_versions:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "unsupported_api_version",
                    "message": f"API version '{api_version}' is not supported",
                    "supported_versions": list(self.supported_versions)
                }
            )

        response = await call_next(request)

        response.headers["X-API-Version"] = api_version or self.current_version

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
        version_header = request.headers.get("X-API-Version")
        if version_header:
            return version_header

        accept = request.headers.get("Accept", "")
        if "version=" in accept:
            try:
                version_part = next(p for p in accept.split(";") if "version=" in p)
                return version_part.split("=")[1].strip()
            except (IndexError, AttributeError):
                pass

        path_parts = request.url.path.split("/")
        if len(path_parts) >= 3 and path_parts[1] == "api":
            potential_version = path_parts[2]
            if potential_version.startswith("v") and potential_version[1:].isdigit():
                return potential_version

        return self.current_version
