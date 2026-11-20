"""
utils/web.py - aiohttp server.

  GET /ad, POST /api/ad/*, GET /monetag/postback   Monetag rewarded-ad Mini App (utils/ads.py)
  GET /<token>            permanent share link -> redirects to the current bot on Telegram
  GET /, /health          readiness: also pings MongoDB (503 when the database is unreachable)
  GET /healthz            liveness: no database call - use THIS as the platform health check, so a MongoDB hiccup
                          does not make Koyeb / Render restart every server at the same moment
  POST /tg/<secret>, /internal/update   multi-server mode only (utils/cluster.py)
  GET|HEAD /dl/<token>/<msg_id>[?d=1]
                          streams one stored file. Range supported (video seeking, resume).
                          ?d=1 forces "Save as" instead of playing inline.

A stream URL is valid only while its share link exists: revoking the link in the panel
also kills every Stream / Download URL that was handed out for it.
"""
import asyncio
import hmac
import logging
import time
from urllib.parse import quote

from aiohttp import web

import config
from database import db
from database.db import settings as S
from utils import ads, cluster
from utils import home, usage
from utils.streamer import RangeError, parse_range, streamer

log = logging.getLogger(__name__)


async def _valid_link(token: str):
    """Share-link lookup. database.get_link keeps hits for a few seconds (a video player fires many Range requests)."""
    return await db.get_link(token)


# ---------------------------------------------------------------------------------------------- protection
_rl: dict = {}        # client ip -> [window start, requests in this window]
RL_WINDOW = 10


def client_ip(request: web.Request) -> str:
    """Real visitor IP. Through our Cloudflare Worker (valid origin secret) the Worker tells us in X-Client-IP; behind one
    proxy (Caddy / Koyeb / Render) the RIGHTMOST X-Forwarded-For entry is the one our own proxy added (the left ones can be faked)."""
    if _via_worker(request):
        ip = request.headers.get("X-Client-IP", "").strip()
        if ip:
            return ip[:64]
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[-1].strip()[:64]
    return request.remote or "?"


def _rate_ok(ip: str) -> bool:
    limit = config.DL_RATE_PER_10S
    if not limit:
        return True
    now = time.monotonic()
    ent = _rl.get(ip)
    if not ent or now - ent[0] >= RL_WINDOW:
        _rl[ip] = [now, 1]
        if len(_rl) > 20000:                                  # forget idle addresses
            for k in [k for k, v in _rl.items() if now - v[0] >= RL_WINDOW]:
                del _rl[k]
        return True
    ent[1] += 1
    return ent[1] <= limit


def _via_worker(request: web.Request) -> bool:
    got = request.headers.get("X-Origin-Secret", "")
    return bool(config.ORIGIN_SECRET) and hmac.compare_digest(got.encode("utf-8", "ignore"),
                                                              config.ORIGIN_SECRET.encode("utf-8", "ignore"))


def _origin_locked() -> bool:
    """Origin lock is on only when BOTH are set: then every link points at PUBLIC_URL (the Worker) and nobody has a reason
    to talk to a server's own koyeb / render address directly."""
    return bool(config.ORIGIN_SECRET and config.PUBLIC_URL)


def _content_disposition(name: str, download: bool) -> str:
    ascii_name = name.encode("ascii", "ignore").decode().replace('"', "") or "file"
    kind = "attachment" if download else "inline"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


async def stream_file(request: web.Request) -> web.StreamResponse:
    if _origin_locked() and not _via_worker(request):
        raise web.HTTPForbidden(text="Use the official link.")
    if not _rate_ok(client_ip(request)):
        raise web.HTTPTooManyRequests(text="Too many requests, slow down.", headers={"Retry-After": str(RL_WINDOW)})
    # Hard cap: a full server says 503 and the Cloudflare Worker simply tries the next server.
    if config.NODE_HARD_STREAMS and usage.live.streams >= config.NODE_HARD_STREAMS and request.method != "HEAD":
        raise web.HTTPServiceUnavailable(text="This server is busy, retrying on another one.", headers={"Retry-After": "3"})
    token = request.match_info["token"]
    try:
        msg_id = int(request.match_info["msg_id"])
    except ValueError:
        raise web.HTTPBadRequest(text="bad message id")

    link = await _valid_link(token)
    if not link or msg_id not in link["ids"]:
        raise web.HTTPNotFound(text="This link is invalid or has been revoked.")
    channel = S.get("db_channel")
    if not channel:
        try:
            await db.settings.load()
        except Exception:
            pass
        channel = S.get("db_channel")
    if not channel or not streamer.ready:
        raise web.HTTPServiceUnavailable(text="Streaming is not available right now.")

    try:
        info = await streamer.get_info(channel["id"], msg_id)
    except Exception:
        log.exception("get_info failed")
        raise web.HTTPBadGateway(text="Could not read the file from Telegram.")
    if not info:
        raise web.HTTPNotFound(text="File no longer available.")

    try:
        start, end, partial = parse_range(request.headers.get("Range"), info.size)
    except RangeError:
        return web.Response(status=416, headers={"Content-Range": f"bytes */{info.size}"})

    headers = {
        "Content-Type": info.mime,
        "Content-Length": str(end - start + 1),
        "Accept-Ranges": "bytes",
        "Content-Disposition": _content_disposition(info.name, request.query.get("d") == "1"),
        "Cache-Control": "private, max-age=0",
        "X-Content-Type-Options": "nosniff",
    }
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{info.size}"
    resp = web.StreamResponse(status=206 if partial else 200, headers=headers)
    await resp.prepare(request)
    if request.method == "HEAD":
        return resp

    gen = streamer.iter_range(info, start, end)
    usage.stream_open()                 # VPS usage tracking: one more viewer right now
    try:
        async for chunk in gen:
            await resp.write(chunk)
            usage.stream_bytes_add(len(chunk))
        await resp.write_eof()
    except (ConnectionResetError, ConnectionError):
        pass  # viewer closed the tab / seeked elsewhere: totally normal
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("Streaming %s/%s failed", token, msg_id)
    finally:
        usage.stream_close()
        await gen.aclose()  # cancels the parallel downloads immediately
    return resp


async def open_link(request: web.Request) -> web.StreamResponse:
    """https://yourdomain/<token>  ->  the CURRENT bot (permanent link, survives a bot change)."""
    if _origin_locked() and not _via_worker(request):
        raise web.HTTPForbidden(text="Use the official link.")
    if not _rate_ok(client_ip(request)):                     # every unknown token is one MongoDB read: scanners must not drain the database
        raise web.HTTPTooManyRequests(text="Too many requests, slow down.", headers={"Retry-After": str(RL_WINDOW)})
    token = request.match_info["token"]
    link = await _valid_link(token)
    if not link:
        raise web.HTTPNotFound(text="This link is invalid or has been revoked.")
    bot = request.app.get("bot")
    if not bot or not bot.username:
        raise web.HTTPServiceUnavailable(text="Please try again in a moment.")
    raise web.HTTPFound(f"https://t.me/{bot.username}?start={token}",
                        headers={"Cache-Control": "no-store"})


async def start_web_server(port: int, bot=None):
    async def health(request):
        try:
            await db.db.command("ping")
            out = {"status": "ok", "streaming": streamer.ready}
            if cluster.ENABLED:
                out["node"] = config.NODE_ID
            return web.json_response(out)
        except Exception as e:
            return web.json_response({"status": "db_error", "error": type(e).__name__}, status=503)

    async def healthz(request):                             # liveness only - never touches MongoDB
        return web.json_response({"status": "ok"})

    async def root(request):
        return web.Response(text="OK")

    app = web.Application()
    app["bot"] = bot
    ads.setup_routes(app)   # /ad (Mini App), /api/ad/*, /monetag/postback
    cluster.setup_routes(app)   # multi-server mode: /tg/<secret> (gateway), /internal/update
    app.router.add_get("/", home.page)                       # landing page (utils/home.py)
    app.router.add_get("/assets/home-image", home.image)
    app.router.add_get("/health", health)
    app.router.add_get("/healthz", healthz)
    app.router.add_route("GET", "/dl/{token}/{msg_id}", stream_file)
    app.router.add_route("HEAD", "/dl/{token}/{msg_id}", stream_file)
    app.router.add_get("/{token:[A-Za-z0-9_-]{6,64}}", open_link)   # keep LAST: fixed routes above win
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    return runner
