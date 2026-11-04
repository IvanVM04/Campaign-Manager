from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/")
def root():
    return {
        "ok": True,
        "service": "D&D Campaign Manager",
        "version": "0.1.0",
    }


@router.get("/health")
def health():
    """Liveness: confirms that the HTTP process is responding."""
    return {
        "ok": True,
    }


@router.get("/ready")
def readiness():
    """Readiness: verifies that SQLite accepts a simple query."""
    from database import get_conn

    try:
        with get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception:  # noqa: BLE001 - readiness maps DB failures to 503
        raise HTTPException(
            status_code=503,
            detail="database unavailable",
        ) from None

    return {
        "ok": True,
        "database": "ready",
    }
