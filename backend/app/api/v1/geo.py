import os

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/geo", tags=["geo"])


@router.get("/reverse")
async def reverse_geocode(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    lang: str = Query("ru", description="Language (accept-language)"),
):
    """Reverse geocode via Nominatim (server-side, no CORS issues).

    Returns:
        {"address_text": "<display_name>", "source": "nominatim"}
    """
    base_url = os.getenv("NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org").rstrip("/")
    user_agent = os.getenv("NOMINATIM_USER_AGENT", "CarBotV2/1.0")

    url = f"{base_url}/reverse"
    params = {
        "format": "jsonv2",
        "lat": lat,
        "lon": lon,
        "zoom": 18,
        "addressdetails": 0,
        "accept-language": lang,
    }

    timeout = httpx.Timeout(5.0, connect=3.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(url, params=params, headers={"User-Agent": user_agent})
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            raise HTTPException(status_code=502, detail="Ошибка геокодирования")

    address_text = data.get("display_name") or ""
    address_text = str(address_text).strip()[:500]

    return {"address_text": address_text, "source": "nominatim"}
