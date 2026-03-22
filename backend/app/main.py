from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import database
from app.db.seed import run_seed


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.run_migrations_on_startup:
        database.run_migrations()
    if settings.run_seed_on_startup:
        db = database.SessionLocal()
        try:
            run_seed(db)
        finally:
            db.close()
    yield
    database.engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


from app.api.routes import pois, trips  # noqa: E402

app.include_router(pois.router, prefix="/api", tags=["pois"])
app.include_router(trips.router, prefix="/api", tags=["trips"])
