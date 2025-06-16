import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from helper.exception_handler import custom_http_exception_handler, global_exception_handler, validation_exception_handler
from config import settings
from database import connect_to_mongodb, close_mongodb_connection
from routes import auth, cases, timeline
from pathlib import Path
from pydantic import ValidationError
from data_processing.data_pre_processing import data_ingestion_pipeline


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# # 
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    print("App is starting up...")
    await connect_to_mongodb()
    async def cron_runner():
        while True:
            print("⏱ Running scrape_content...")
            try:
                await data_ingestion_pipeline(limit=2)
            except Exception as e:
                print("Error in scrape_content cron:", e)
            await asyncio.sleep(300)  # Sleep 5 minutes

    asyncio.create_task(cron_runner())  # Schedule background task
    yield
    # Shutdown actions
    print("App is shutting down...")
    await close_mongodb_connection()


# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    docs_url=f"{settings.API_PREFIX}/docs",
    redoc_url=f"{settings.API_PREFIX}/redoc",
    debug=settings.DEBUG,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Create uploads directory
uploads_dir = Path("./uploads")
uploads_dir.mkdir(exist_ok=True)

# Mount static files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Exception handlers
app.add_exception_handler(HTTPException, custom_http_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)
app.add_exception_handler(ValidationError, validation_exception_handler)


# Include routers
app.include_router(auth.router,
    prefix=f"{settings.API_PREFIX}/auth",
    tags=["authentication"],
)

app.include_router(cases.router,
    prefix=f"{settings.API_PREFIX}/cases",
    tags=["case-management"],
)

app.include_router(timeline.router,
    prefix=f"{settings.API_PREFIX}/timeline",
    tags=["timeline"],
)

# Root endpoint
@app.get("/", include_in_schema=False)
async def root():
    return {"message": f"Welcome to {settings.APP_NAME}, server is running!"}


# from fastapi import FastAPI, Request
# from fastapi.responses import HTMLResponse
# from fastapi.templating import Jinja2Templates
# from fastapi.staticfiles import StaticFiles

# # app = FastAPI()

# # Serve HTML templates
# templates = Jinja2Templates(directory="templates")

# # Route to render the graph HTML page
# @app.get("/graph", response_class=HTMLResponse)
# async def show_graph_page(request: Request):
#     return templates.TemplateResponse("graph.html", {"request": request})