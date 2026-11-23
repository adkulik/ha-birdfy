"""API client tests against a fake Birdfy server."""
from aiohttp import web
import pytest

from custom_components.birdfy import api as api_mod
from custom_components.birdfy.api import BirdfyApi, BirdfyAuthError, hash_password


@pytest.fixture
async def fake(socket_enabled, aiohttp_server, monkeypatch):
    state = {"logins": 0, "expire_once": True}

    async def login(request):
        body = await request.json()
        state["logins"] += 1
        if body["password"] != hash_password("ok"):
            return web.json_response({"ret": 1001, "msg": "bad"})
        return web.json_response({"ret": 0, "token": "TOK", "userID": 7, "region": "eu-central-1"})

    async def devices(request):
        assert request.headers["x-nvs-signature"]
        return web.json_response({"devices": [{"serialNumber": "S1", "deviceName": "Feeder"}]})

    async def events(request):
        if state["expire_once"]:
            state["expire_once"] = False
            return web.json_response({}, status=401)
        return web.json_response({"events": [
            {"alarmId": "a1", "alertTime": 1700000000000, "aiRecognitionStatus": "auto_success",
             "pic": "b:k/1.jpeg", "pictureList": "b:k/1.jpeg,b:k/2.jpeg", "type": 50,
             "description": '{"recordDir": "b:rec/", "aiLabels": {"1": [{"name": "bird", "objects": [{"desc": "Blue Tit", "track": "1"}]}]}}'},
            {"alarmId": "a2", "alertTime": 1700000100000, "aiRecognitionStatus": "auto_nobirds", "description": "bad json"},
        ]})

    async def download_link(request):
        body = await request.json()
        item = body["eventList"][0]
        assert item["serialnumber"] == "S1" and item["dataGroup"] == ["pic"]
        assert item["pictureList"] == ["b:k/1.jpeg", "b:k/2.jpeg"]
        assert item["recordDir"] == "b:rec/"
        return web.json_response({"eventList": [{"alarmId": item["alarmId"],
            "picList": [str(request.url.with_path("/img.jpg"))]}]})

    async def img(request):
        return web.Response(body=b"JPEG")

    app = web.Application()
    app.router.add_post("/login", login)
    app.router.add_get("/v1/devices/v3", devices)
    app.router.add_get("/devices/{sn}/events", events)
    app.router.add_post("/event/downloadLink", download_link)
    app.router.add_get("/img.jpg", img)
    server = await aiohttp_server(app)
    base = str(server.make_url(""))
    monkeypatch.setattr(api_mod, "LOGIN_URL", base + "/login")
    monkeypatch.setattr(api_mod, "DEFAULT_LOCAL_ENDPOINT", base)
    monkeypatch.setattr(api_mod, "CENTRAL_API", base)
    monkeypatch.setattr(BirdfyApi, "api_base", property(lambda self: base))
    return state


async def test_flow(fake, aiohttp_client_session=None):
    import aiohttp
    async with aiohttp.ClientSession() as s:
        api = BirdfyApi(s, "A@B.hu", hash_password("ok"), "android-1")
        devs = await api.async_get_devices()
        assert devs[0].serial == "S1" and devs[0].name == "Feeder"
        evs = await api.async_get_events("S1", 10)
        assert [e.alarm_id for e in evs] == ["a2", "a1"]  # newest first
        assert not evs[0].is_bird and evs[0].species == []
        assert evs[1].is_bird and evs[1].primary_species == "Blue Tit" and evs[1].bird_count == 1
        assert evs[1].timestamp == 1700000000
        assert fake["logins"] == 2  # re-login after 401
        assert await api.async_get_event_picture("S1", evs[1]) == b"JPEG"

        bad = BirdfyApi(s, "a@b.hu", hash_password("nope"), "android-1")
        with pytest.raises(BirdfyAuthError):
            await bad.async_login()


def test_generic_bird_label_dropped_next_to_species():
    import json, time
    from custom_components.birdfy.api import BirdfyEvent

    def make(*labels):
        frames = {str(i): [{"name": "bird", "objects": [{"desc": n, "confidence": 80, "track": str(i)}]}]
                  for i, n in enumerate(labels)}
        return BirdfyEvent.from_api({"type": 50, "alarmId": "x", "alertTime": int(time.time() * 1000),
                                     "description": json.dumps({"aiLabels": frames}),
                                     "aiRecognitionStatus": "auto_success"})

    assert make("Great Tit", "Bird", "Great Tit").species == ["Great Tit"]
    assert make("Bird", "Bird").species == ["Bird"]  # nothing better to show
