# Multi-server checklist (ONE bot, many servers)

Two servers have `NODE_ROLE=gateway`, all others `NODE_ROLE=worker`.
The gateways compete for a lease in MongoDB: **one is the active gateway** (owns the Telegram webhook, the admin panel and the
background jobs), the other is a **hot standby** that works like a worker until it has to take over (about 40 s after the active one
dies, a few seconds after a clean deploy; Telegram keeps the updates meanwhile).

| Server | NODE_ID | NODE_ROLE | BASE_URL |
|---|---|---|---|
| #1 (most stable) | n1 | gateway | its own https URL |
| #2 | n2 | gateway (standby) | its own https URL |
| #3, #4 ... | n3, n4 ... | worker | its own https URL (Render: leave empty) |

Same on ALL: BOT_TOKEN, MONGO_URI, DB_NAME, OWNER_ID, API_ID, API_HASH, CLUSTER_SECRET (min 24 characters: `openssl rand -hex 32`).
Different on each: NODE_ID, BASE_URL (VPS: DOMAIN), NODE_ROLE (gateway or worker).

## Deploy / update
1. Roll the servers **one at a time** (workers first, then the standby gateway, the active gateway last).
   A stopping server hands the lease over and drains its running requests (`DRAIN_SECONDS`, keep it below the platform's grace period).
2. Check `https://<server>/healthz` (liveness) and `https://<server>/health` (also pings MongoDB).
3. Bot -> Panel -> Servers: every server is listed under its own name, `*` = active gateway, `~` = standby.
   Only 1 server listed = NODE_ID is duplicated.
4. Platform health check path = **`/healthz`** (Koyeb: Settings -> Health checks; Render: `render.yaml` already has it).
   `/health` needs MongoDB; as a platform check one MongoDB hiccup would restart every server at once.

## Several MongoDB clusters (optional)
`MONGO_URI` = your own cluster = **core**. Add `MONGO_URI_2` (+ `MONGO_URI_3`) with the same value on **every** server:
| Cluster | Holds | If it dies |
|---|---|---|
| core (`MONGO_URI`) | settings, users, links, files, server list + gateway lease, autoposter, user-account session | bot is down (it always was) |
| hot (`MONGO_URI_2`) | daily-limit counters, ad sessions, daily stats, auto-delete queue | servers use core meanwhile (about 15 s to notice, then automatic) |
| logs (`MONGO_URI_3`) | VPS usage + cluster statistics | same |
These collections can **never** be moved off core (`database/mongo.py: CORE_ONLY`): a cluster you do not control must not hold your users,
your links, the login of your Telegram account or the server list (the gateway sends requests to the URLs in it).
Atlas: Network Access `0.0.0.0/0` (Koyeb/Render IPs change) + a long random password per database user. Free clusters allow 500 connections
in total: `MONGO_MAX_POOL` (default 20) x servers must stay far below that, also counting your friend's own apps.
Panel -> Stats shows every cluster (storage, ping, connections, which collections it holds).

## Updating an existing multi-server setup to this version (HMAC server-to-server auth)
Servers used to send the raw `CLUSTER_SECRET` to every URL in the server list. They now send an HMAC signature (timestamp + target node + body).
1. Add `CLUSTER_ALLOW_LEGACY=1` on all servers and deploy them one by one (workers first, gateways last).
2. When all run the new code, remove `CLUSTER_ALLOW_LEGACY` and deploy again. Rotate `CLUSTER_SECRET` if a server list was ever writable by others.

## Protection (recommended)
- `PUBLIC_URL=https://<your domain>` on all servers and the Cloudflare Worker in front (see cloudflare-worker/README.md).
- `ORIGIN_SECRET` = the same random text in the Worker (secret) and on every server: the servers then answer `/dl/...` and `/<token>`
  only when the request came through the Worker, so the koyeb / render addresses cannot be used to bypass it. Needs `DL_MODE=proxy`.
- `DL_RATE_PER_10S` (default 60) limits requests per visitor IP; `NODE_HARD_STREAMS` / `NODE_HARD_TASKS` are the real limits where a
  server answers 503 (the Worker and the gateway then use another server).
- VPS + Caddy: `CLUSTER_ALLOW` = public IPs of the gateway servers (they are the only ones calling `/internal/update`),
  `TG_ALLOW="149.154.160.0/20 91.108.4.0/22"` on the gateways = only Telegram may call the webhook (not behind Cloudflare's orange cloud).

## Known limits (be aware)
- A hard crash (power loss, OOM kill) loses the updates that were being processed on that server at that moment; a normal redeploy does not.
- All servers use ONE bot token, so Telegram's send limit (about 30 messages / second for the bot) is shared. More servers add
  Stream/Download bandwidth and CPU, not Telegram send rate.
- MongoDB (core) is the shared dependency (routing list, lease, settings). Use a paid / dedicated cluster for production, not a free M0.
- Settings changed in the panel reach workers after up to ~30 s. A revoked link can still open for up to 15 s on OTHER servers.
- The admin panel keeps its state (e.g. a half-finished Batch upload) in the gateway's memory: a gateway change / redeploy loses it.
- With a secondary cluster down, the daily-limit counters restart from 0 on core (users may get a few extra links that day).
- The server list holds each server's URL: only https URLs to public hosts are used by the gateway (private IPs / localhost are refused).
