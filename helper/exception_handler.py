from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError


async def custom_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail},
    )
    

# Exception handlers
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


async def validation_exception_handler(request: Request, exc: ValidationError):
    # Extract the first error message (customize as needed)
    # error_details = exc.errors()
    # if error_details:
    #     msg = error_details[0].get("msg", "Invalid input.")
    # else:
    msg = "Invalid input."
    return JSONResponse(
        status_code=422,
        content={"message": msg}
    )
