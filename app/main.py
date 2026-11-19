from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app.keitaro import KeitaroApiError, KeitaroClient
from app.models import CampaignCreationLog
from app.schemas import CreateCampaignRequest

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.database_url.startswith("sqlite"):
        Path("data").mkdir(exist_ok=True)
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Keitaro Campaign Wrapper", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(KeitaroApiError)
async def keitaro_error_handler(_: Request, exc: KeitaroApiError) -> JSONResponse:
    return JSONResponse(
        status_code=502 if exc.status_code >= 500 else 400,
        content={"detail": str(exc), "keitaro_status": exc.status_code, "errors": exc.details},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/lookups")
async def lookups() -> dict[str, list[dict[str, Any]]]:
    async with KeitaroClient(settings) as client:
        return await client.list_resources()


@app.post("/api/campaigns", status_code=201)
async def create_campaign(
    payload: CreateCampaignRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    async with KeitaroClient(settings) as client:
        campaign, streams = await client.create_campaign(payload)

    db.add(
        CampaignCreationLog(
            campaign_id=campaign.get("id") if isinstance(campaign, dict) else None,
            name=payload.name.strip(),
            geo_code=payload.geo_code,
            offer_id=payload.offer_id,
            request_payload=payload.model_dump(),
            response_payload={"campaign": campaign, "streams": streams},
        )
    )
    db.commit()
    campaign_url = campaign.get("url") if isinstance(campaign, dict) else None
    return {"campaign": campaign, "streams": streams, "campaign_url": campaign_url}


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "keitaro_configured": str(bool(settings.keitaro_api_key)).lower()}
