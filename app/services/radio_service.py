import httpx

RADIO_BROWSER_URL = "https://de1.api.radio-browser.info/json"

async def get_tunisian_radios():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{RADIO_BROWSER_URL}/stations/bycountrycodeexact/TN", params={"limit": 100, "order": "clickcount", "reverse": "true", "hidebroken": "true"})
        return resp.json()

async def search_radios(query: str, country: str = None):
    params = {"limit": 100, "order": "clickcount", "reverse": "true", "hidebroken": "true"}
    if country: params["countrycode"] = country
    if query: params["name"] = query
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{RADIO_BROWSER_URL}/stations/search", params=params)
        return resp.json()
