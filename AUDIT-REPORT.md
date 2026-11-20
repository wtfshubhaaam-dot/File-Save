# Audit: multi-server (5-6 servers) + multi-MongoDB

Scope: poora project (`main.py`, `config.py`, `database/`, `utils/`, `handlers/`, Caddy / Docker / Render / Cloudflare Worker).
Method: code padha, har process-local state aur har MongoDB write path trace kiya, fixes likhe, fake-Mongo tests se verify kiye.

**Verification ki limit:** is environment me real MongoDB / Telegram / package install nahi tha. Isliye tests stubs aur fake Motor se chale
(`tests/test_multiserver.py` 72 pass, `tests/test_mongo_router.py` 37 pass). `$$NOW` lease pipeline aur Atlas ka real behaviour maine
nahi chheda aur nahi chalaya. **Live karne se pehle 2 servers pe staging test zaroor karo** (checklist neeche).

---

## 1. Aapka MongoDB sawaal: dost ke 2 URL + aapka URL

Design: `database/mongo.py` (naya). Teen cluster, ek hi code.

| Cluster | Env | Kya rakhta hai | Down ho to |
|---|---|---|---|
| **core** = aapka | `MONGO_URI` | settings, users, links, files, server list + gateway lease, autoposter, transfer session, known_chats | bot down (pehle bhi yahi tha) |
| **hot** = dost #1 | `MONGO_URI_2` | `daily_usage` (limit counters), `ad_sessions`, `daily_stats`, `pending_deletes` | ~15 s me auto core pe fallback |
| **logs** = dost #2 | `MONGO_URI_3` | `vps_usage`, `cluster_stats` (sirf statistics) | hot pe, warna core pe |

**Kya hard-coded roka hai (`CORE_ONLY`)** - ye dost ke cluster pe kabhi nahi ja sakte, `MONGO_ROUTES` se bhi nahi:
- `users`: aapka poora audience (user IDs). Dost ke paas copy hona = aapka asset leak.
- `links`, `files`, `ap_*`: link table / posts.
- `transfer`: **aapke personal Telegram account ka session string plaintext me** hai. Ye kisi aur ke cluster pe gaya to account takeover.
- `cluster_nodes`, `cluster_lease`, `cluster_assign`: control plane. Gateway `cluster_nodes` ke URLs pe request bhejta hai; jo us collection ko likh sakta hai
  wo servers ko apne URL pe bhej sakta tha (neeche S1).

**Dost ke cluster pe kya dikhega (privacy):** user IDs + link tokens (`ad_sessions`, `pending_deletes`), daily counts. Files ya users ki list nahi.
Agar ye bhi nahi chahiye: `MONGO_ROUTES=ad_sessions=core,pending_deletes=core`.
Dost chahe to counters badal sakta hai (limit bypass) - isliye sirf expendable data wahan hai.

**Fallback kaise kaam karta hai:** failed call usi waqt core pe retry hoti hai, cluster 45 s ke liye "down" mark hota hai, background monitor har 15 s ping karke
wapas up karta hai. Koi 15 s intezar nahi (secondary timeout 4 s, core 15 s). Startup pe dost ka cluster dead ho to bot phir bhi start hota hai.
Sab indexes (TTL sameet) har us cluster pe bante hain jahan collection ja sakta hai, fallback core pe bhi.

**Load asar (code padh ke andaza, measure nahi kiya):** ek normal link-open (forward mode, ads off) pehle ~6-7 DB ops tha
(`get_link`, `claim_quota`, `caption_overrides`, `inc_views` = 2 write, `touch_user`...). Ab ~2-3 hai, aur unme se core pe sirf 1-2.
Core pe ab sirf `users` write + cache-miss reads aate hain.

Atlas free tier ke hisaab se limits: M0 ~100 ops/s throttle, **500 connections total**. 6 server x `maxPoolSize=50` = 300 connection ek hi cluster pe
(dost ke apne apps ke connections alag se). Ab default `MONGO_MAX_POOL=20` (cluster mode me). Atlas me Network Access `0.0.0.0/0` chahiye
(Koyeb/Render IP badalte hain), isliye **har cluster ka password lamba aur alag** rakho.

---

## 2. Findings aur status

Severity: **C** critical, **H** high, **M** medium, **L** low.  `FIXED` = is zip me code badla hai.  `OPEN` = sirf recommendation.

### Security
| # | Sev | Problem | Status |
|---|---|---|---|
| S1 | **C** | `cluster.forward()` har node ke URL pe **raw `CLUSTER_SECRET`** header me bhejta tha. URL `cluster_nodes` (MongoDB) se aata hai. Jo bhi us collection ko likh sake (dost ka cluster, leaked URI, 0.0.0.0/0 + weak password) apna URL daal ke secret chura leta, phir `/internal/update` pe **OWNER_ID ka fake update** bhej ke admin panel / broadcast / transfer chala sakta tha. | **FIXED**: ab HMAC(timestamp + receiver node id + body), 60 s validity. Secret kabhi network pe nahi jaata. Purane servers ke liye rollout mode `CLUSTER_ALLOW_LEGACY=1` (baad me hata do). |
| S2 | H | `transfer` collection me user-account session string plaintext. | **Partly**: core-only guard laga. OPEN: Atlas DB user ko least privilege do, URI kabhi share na karo. Aur behtar: session string ko `BOT_TOKEN`-independent key se encrypt karna (naya dependency chahiye). |
| S3 | M | `/<token>` route pe rate limit nahi tha: random tokens se scanner har request pe ek Mongo read karwata (negative result cache nahi hota). 6 servers = M0 ka 100 ops/s turant khatam. | **FIXED**: per-IP limit (`DL_RATE_PER_10S`) ab yahan bhi. Note: bina `ORIGIN_SECRET` ke Worker ke peeche sab visitors ek hi IP dikhte hain; `ORIGIN_SECRET` zaroor set karo. |
| S4 | L | Monetag postback me `hmac.compare_digest` str pe: non-ASCII secret = 500. | **FIXED** (bytes compare, 403). |
| S5 | L | `.env.example` me `CLUSTER_ALLOW` default `0.0.0.0/0`. | Ab HMAC hai, isliye kam critical. Phir bhi gateway IPs daalo. |

### Multi-server correctness
| # | Sev | Problem | Status |
|---|---|---|---|
| M1 | **H** | `vps_usage` ka `_id` sirf `YYYY-MM-DD-HH` tha: **saare servers ek hi document me** `$inc`/`$max` karte the. CPU/RAM/cores/bandwidth mix, "Plan advice" kisi aise server ke liye jo exist nahi karta. | **FIXED**: `_id = hour|node`, `node` field, panel apne server ka data dikhata hai (purana data bhi dikhta hai). |
| M2 | H | Gateway pe Telegram retry same update dobara route kar sakta tha (dedupe sirf receiving node pe tha, retry doosre node pe ja sakta tha) = **double delivery**. | **FIXED**: gateway-level dedupe (last 4000 update ids). |
| M3 | H | Monetag postback URL gateway ke apne `BASE_URL` pe fix. Gateway badla / mara to postbacks fail, ads "verifying" pe atak jaate. | **FIXED**: `PUBLIC_URL` set ho to postback URL wahi use hota hai, Worker `/monetag/postback` (sirf yahi) allow karta hai. **Aapko Monetag me postback URL dobara paste karna hoga** (Panel -> Ads). |
| M4 | M | Hot single documents: har click `daily_stats/<aaj>` aur `links/<token>.views` pe `$inc` (5-6 servers = write contention + ops waste). | **FIXED**: memory me jod ke har 5 s me ek write (`views` bulk). Crash pe max ~5 s ke counters lose. |
| M5 | M | `get_link` / `caption_overrides` har click pe DB read. | **FIXED**: 15 s / 60 s per-server cache (sirf hits; naya link turant khulta hai; revoke us server pe turant, doosre servers pe <=15 s). |
| M6 | M | `schedule_delete` fail ho to exception files bhejne **ke baad** aati (user ko error, quota refund nahi). | **FIXED**: log hota hai, raise nahi. |
| M7 | M | Ad gate: ad-session store down => unhandled exception, user ko kuch nahi. | **FIXED**: "ad ke bina deliver" fallback + log. |
| M8 | M | `users` pe `banned`/`blocked` count har baar full scan. | **FIXED**: 2 partial indexes. |
| M9 | M | MongoDB pool 50 x servers. | **FIXED** (default 20 cluster mode me, env se). |
| M10 | M | Admin panel state (jaise adhura Batch upload) gateway ki memory me. Gateway change / redeploy = state gaya. | **OPEN**. Deploy ke waqt admin batch na chalao. |
| M11 | M | Settings workers pe ~30 s late pahunchti hain. | **OPEN** (documented). Chahiye to version-counter polling banao. |
| M12 | M | Har node MTProto (`pyrofork`) session `in_memory=True` se **naya auth key** har start pe banata hai. Sab servers ek saath restart/crash-loop = Telegram `FLOOD_WAIT` on login. | **OPEN**: servers ek-ek karke deploy karo (pehle se doc me hai). Ya session persist karo. |
| M13 | L | Hard crash me jo updates process ho rahe the wo lost. | OPEN (design limit, documented). |
| M14 | L | `claim_quota` fallback: hot down ho to counters core pe 0 se shuru, us din kuch users ko extra links. | Accepted, documented. |
| M15 | L | Stale duplicate `env.example` (purani baat likhi hai, "exactly ONE gateway"). | OPEN: delete kar do, `.env.example` hi rakho. |

### Jo limit multi-server se **nahi** badhegi
- Telegram bot ka send limit (~30 msg/s) **ek bot token ka hai, saare servers ke liye shared**. `delivery_mode=forward` me 6 server bhi 30 msg/s se
  zyada nahi bhej sakte. Stream/Download mode (web links) hi bandwidth/CPU scale karta hai. Isliye 5-6 servers ka fayda zyada tar stream mode me hai.
- MongoDB ab bottleneck nahi rahega, par Telegram rate limit rahega.

---

## 3. Kya badla (files)
`database/mongo.py` (naya), `database/db.py`, `config.py`, `utils/cluster.py`, `utils/usage.py`, `utils/ads.py`, `utils/web.py`, `utils/backup.py`,
`main.py`, `handlers/admin.py` (Stats me har cluster), `cloudflare-worker/hub-router.js`, `.env.example`, `render.yaml`, `FIX-MULTISERVER.md`,
`tests/test_multiserver.py` (HMAC/dedupe tests), `tests/test_mongo_router.py` (naya).

## 4. Live karne ka checklist
1. **Backup lo** (Panel -> Backup) pehle.
2. Dost ke clusters me ek **alag database user** + lamba password banwao; Atlas Network Access `0.0.0.0/0`. Unse puchho ki ye theek hai (free tier unka hai, wo pause/band kar sakte hain).
3. Har server pe same env: `MONGO_URI` (aapka), `MONGO_URI_2`, `MONGO_URI_3`, `MONGO_MAX_POOL=20`.
4. **Update order:** sab pe `CLUSTER_ALLOW_LEGACY=1` -> workers ek-ek karke -> standby gateway -> active gateway sabse last. Sab ho jaye to `CLUSTER_ALLOW_LEGACY` hatao, dobara deploy.
5. Check: `/healthz`, `/health`, Panel -> Servers (sab dikhe), Panel -> Stats (teeno cluster dikhe aur "📚" me sahi collections).
6. **Failover test:** staging me dost ka URI galat kar do -> bot chalta rahe, logs me `cluster 'hot' is DOWN`, Stats me 🔴 "core is serving". Sahi karo -> 15 s me `is back`.
7. `PUBLIC_URL` + `ORIGIN_SECRET` set karke Worker deploy karo (naya `hub-router.js`), phir **Monetag me postback URL update** karo.
8. Ek test link 2 alag accounts se kholo, daily limit counter check karo (hot cluster me `daily_usage` dikhna chahiye).
