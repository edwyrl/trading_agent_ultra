from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.container import Container
from contracts.enums import SignalRunStatus
from contracts.signals_contracts import DashboardPayloadDTO, SignalArtifactDTO, SignalPluginMetaDTO, SignalRunRequestDTO, SignalRunStatusDTO
from shared.db.session import get_db_session

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.post("/runs", response_model=SignalRunStatusDTO)
def create_run(
    request: SignalRunRequestDTO,
    session: Session = Depends(get_db_session),
) -> SignalRunStatusDTO:
    container = Container(session=session)
    service = container.signal_service()
    result = service.submit_run(request)
    session.commit()
    return result


@router.get("/runs", response_model=list[SignalRunStatusDTO])
def list_runs(
    status: SignalRunStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> list[SignalRunStatusDTO]:
    container = Container(session=session)
    service = container.signal_service()
    return service.list_runs(status=status, limit=limit, offset=offset)


@router.get("/runs/{run_id}", response_model=SignalRunStatusDTO)
def get_run(run_id: str, session: Session = Depends(get_db_session)) -> SignalRunStatusDTO:
    container = Container(session=session)
    service = container.signal_service()
    run = service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    return run


@router.get("/runs/{run_id}/dashboard", response_model=DashboardPayloadDTO)
def get_dashboard(run_id: str, session: Session = Depends(get_db_session)) -> DashboardPayloadDTO:
    container = Container(session=session)
    service = container.signal_service()
    try:
        return service.get_dashboard(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/artifacts", response_model=list[SignalArtifactDTO])
def list_artifacts(run_id: str, session: Session = Depends(get_db_session)) -> list[SignalArtifactDTO]:
    container = Container(session=session)
    service = container.signal_service()
    run = service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    return service.list_artifacts(run_id)


@router.post("/runs/{run_id}/cancel", response_model=SignalRunStatusDTO)
def cancel_run(run_id: str, session: Session = Depends(get_db_session)) -> SignalRunStatusDTO:
    container = Container(session=session)
    service = container.signal_service()
    try:
        result = service.cancel_run(run_id)
    except ValueError as exc:
        detail = str(exc)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail) from exc
        raise HTTPException(status_code=409, detail=detail) from exc
    session.commit()
    return result


@router.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: str, session: Session = Depends(get_db_session)) -> None:
    container = Container(session=session)
    service = container.signal_service()
    try:
        deleted = service.delete_run(run_id)
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=409, detail=detail) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    session.commit()


@router.get("/plugins", response_model=list[SignalPluginMetaDTO])
def list_plugins(session: Session = Depends(get_db_session)) -> list[SignalPluginMetaDTO]:
    container = Container(session=session)
    service = container.signal_service()
    return service.list_plugins()
