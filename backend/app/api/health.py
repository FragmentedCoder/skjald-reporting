from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check for the proxy and orchestrator; checks no secrets, no database."""
    return {"status": "ok"}
