from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app.editor import (
    EditorError,
    _stream_payload,
    add_offer,
    bring_back_offer,
    campaign_payload,
    cancel_stream,
    fetch_campaign,
    pin_offer,
    push_stream,
    remove_offer,
    search_offers,
)
from app.keitaro import KeitaroApiError, KeitaroClient
from app.models import CampaignCreationLog, ManagedCampaign
from app.schemas import (
    AddOfferRequest,
    CreateCampaignRequest,
    FetchStreamsRequest,
    PinOfferRequest,
)

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


@app.exception_handler(EditorError)
async def editor_error_handler(_: Request, exc: EditorError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc), "errors": exc.details},
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


@app.get("/api/editor/campaigns")
async def editor_campaigns() -> dict[str, list[dict[str, Any]]]:
    async with KeitaroClient(settings) as client:
        return {"campaigns": await client.list_campaigns()}


@app.get("/api/editor/campaigns/{campaign_id}")
async def get_editor_campaign(campaign_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    campaign = db.scalar(
        select(ManagedCampaign).where(ManagedCampaign.keitaro_campaign_id == campaign_id)
    )
    if campaign is None:
        raise EditorError(
            "Кампания ещё не импортирована. Нажми "
            "Fetch Streams from KT.",
            status_code=404,
        )
    return campaign_payload(campaign)


@app.post("/api/editor/campaigns/{campaign_id}/fetch")
async def fetch_editor_campaign(
    campaign_id: int,
    payload: FetchStreamsRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    async with KeitaroClient(settings) as client:
        campaign = await fetch_campaign(
            db, client, campaign_id, discard_pending=payload.discard_pending
        )
    db.commit()
    return campaign_payload(campaign)


@app.get("/api/editor/offers")
async def editor_offers(query: str = "") -> dict[str, list[dict[str, Any]]]:
    async with KeitaroClient(settings) as client:
        return {"offers": await search_offers(client, query)}


@app.post("/api/editor/streams/{stream_id}/offers")
async def editor_add_offer(
    stream_id: int, payload: AddOfferRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    async with KeitaroClient(settings) as client:
        stream = await add_offer(db, client, stream_id, payload.offer_id)
    db.commit()
    return {"stream": _stream_response(stream)}


@app.post("/api/editor/streams/{stream_id}/offers/{offer_id}/remove")
async def editor_remove_offer(
    stream_id: int, offer_id: int, db: Session = Depends(get_db)
) -> dict[str, Any]:
    stream = remove_offer(db, stream_id, offer_id)
    db.commit()
    return {"stream": _stream_response(stream)}


@app.post("/api/editor/streams/{stream_id}/offers/{offer_id}/bring-back")
async def editor_bring_back_offer(
    stream_id: int, offer_id: int, db: Session = Depends(get_db)
) -> dict[str, Any]:
    stream = bring_back_offer(db, stream_id, offer_id)
    db.commit()
    return {"stream": _stream_response(stream)}


@app.post("/api/editor/streams/{stream_id}/offers/{offer_id}/pin")
async def editor_pin_offer(
    stream_id: int,
    offer_id: int,
    payload: PinOfferRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    stream = pin_offer(db, stream_id, offer_id, payload.pinned)
    db.commit()
    return {"stream": _stream_response(stream)}


@app.post("/api/editor/streams/{stream_id}/cancel")
async def editor_cancel_stream(stream_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    stream = cancel_stream(db, stream_id)
    db.commit()
    return {"stream": _stream_response(stream)}


@app.post("/api/editor/streams/{stream_id}/push")
async def editor_push_stream(stream_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    async with KeitaroClient(settings) as client:
        stream = await push_stream(db, client, stream_id)
    db.commit()
    return {"stream": _stream_response(stream)}


def _stream_response(stream: Any) -> dict[str, Any]:
    return _stream_payload(stream)
