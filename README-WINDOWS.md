# Running CloudSLA-Recommender on Windows

This guide is for setting up the project on a fresh Windows 10/11 machine.
The whole stack runs inside Docker — you do **not** need to install Python,
Node, Postgres, or Redis on the host. You only need Docker Desktop.

If you're carrying state (a populated database, ingested PDFs, ChromaDB
embeddings) over from another machine, see the **Migrating from another
machine** section at the bottom.

---

## 1. Prerequisites

| Software | Why | Where to get it |
|---|---|---|
| **Docker Desktop for Windows** | Runs all containers (api, frontend, postgres, redis, chromadb, libretranslate, celery_worker, celery_beat) | https://www.docker.com/products/docker-desktop/ |
| **WSL 2** | Docker Desktop's required backend on Windows | Docker installer will set this up for you. Manual instructions: https://learn.microsoft.com/en-us/windows/wsl/install |
| **Git for Windows** | Cloning the repo | https://git-scm.com/download/win |
| **Windows Terminal** *(optional but nicer)* | Better shell experience than `cmd.exe` | Microsoft Store |
| **VS Code + WSL extension** *(optional)* | Native-speed editing inside WSL | https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-wsl |

### Recommended host specs

| Resource | Minimum to run | Recommended |
|---|---|---|
| RAM | 8 GB total (allocate 4 GB to Docker) | **16 GB** (allocate 6–8 GB to Docker) |
| Disk free | 20 GB | 40 GB (images + HuggingFace model cache + ChromaDB) |
| CPU | x64 with VT-x / AMD-V enabled in BIOS | Quad-core or better |

The embedding model `multilingual-e5-base` and ChromaDB together use ~2 GB at
idle. Under 6 GB allocated to Docker you will see OOM-kills, especially on
the first query that loads the model.

To raise Docker's memory ceiling:
**Docker Desktop → Settings → Resources → Memory → set to 6 GB+ → Apply & Restart**

---

## 2. One-time setup

### 2.1  Tell Git to leave line endings alone

This is the **single most important Windows step**. Windows Git, by default,
converts text files to CRLF on checkout — which breaks shell scripts and
Python files inside the Linux containers.

Run **once, globally, before cloning**:

```powershell
git config --global core.autocrlf input
```

The repo also ships a `.gitattributes` that enforces LF for all text files,
so even without the global setting you'll be safe — but doing both is the
belt-and-braces approach.

### 2.2  Clone the repo

You have two choices for *where* to clone. The choice affects performance
significantly:

| Location | Hot-reload speed | When to choose |
|---|---|---|
| **Inside WSL** (e.g. `\\wsl$\Ubuntu\home\<you>\CloudSLA-Recommender`) | Native Linux speed | Active development, frequent code edits |
| **On Windows** (e.g. `C:\Users\<you>\CloudSLA-Recommender`) | Slow (Windows ↔ Linux FS bridge) | Demo / viva only — you're not editing files |

**For viva or one-off demo, plain Windows is fine.** For active dev, clone
inside WSL.

```powershell
# Option A — Windows side (simple)
cd C:\Users\<you>
git clone <your-repo-url> CloudSLA-Recommender
cd CloudSLA-Recommender
```

```bash
# Option B — inside WSL (faster dev loop)
wsl
cd ~
git clone <your-repo-url> CloudSLA-Recommender
cd CloudSLA-Recommender
```

### 2.3  Create your `.env`

The repo ships `.env.example` but not `.env` (the real one isn't
checked in — it may contain admin keys, API keys, etc).

```powershell
copy .env.example .env
```

Then open `.env` in any editor and fill in values. At minimum you'll
want to set:

```
ADMIN_API_KEY=dev-admin-key
POSTGRES_USER=user
POSTGRES_PASSWORD=password
POSTGRES_DB=cloudsla
```

If you have a Google Cloud Billing API key for live GCP pricing, add:

```
GCP_BILLING_API_KEY=AIza...
```

(Without it, GCP pricing falls back to a curated dataset — still works,
just not live.)

### 2.4  Sanity-check Docker

```powershell
docker --version
docker compose version
docker info
```

You should see Docker engine info and **no errors**. If Docker Desktop
isn't running, start it from the Start menu and wait for the whale icon
in the system tray to go solid (not animated).

---

## 3. Starting the stack

From the project root:

```powershell
docker compose up --build -d
```

First run pulls/builds 8 images (~3 GB total download) and takes
**10–20 minutes** depending on connection speed. Subsequent runs take
~30 seconds because Docker caches everything.

Watch progress:

```powershell
docker compose logs -f api
```

The api is ready when you see:

```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

…and the healthcheck stabilises. You can check it directly:

```powershell
curl http://localhost:8000/health
# {"status":"ok"}
```

### 3.1  Open the UI

http://localhost:3000

That's the React frontend served by nginx. Everything is reachable from
your Windows browser even though it's running in WSL — Docker Desktop
forwards the ports for you.

### 3.2  Stop the stack

```powershell
docker compose down            # stop containers, keep data volumes
docker compose down -v         # stop AND wipe Postgres + ChromaDB volumes (clean slate)
```

---

## 4. Common Windows gotchas

### 4.1  "Ports are not available" / "bind: address already in use"

Something on Windows is squatting on a port we need. Check:

| Port | Used by |
|---|---|
| 3000 | frontend nginx |
| 8000 | FastAPI |
| 5432 | Postgres |
| 5001 | LibreTranslate |
| 6379 | Redis |
| 8001 | ChromaDB |

Find the offender:

```powershell
netstat -ano | findstr :5432
```

…then either stop that process (often a local Postgres install) or
edit `docker-compose.yml` to remap the port:

```yaml
postgres:
  ports:
    - "5433:5432"   # host:container — move postgres to 5433 on the host
```

### 4.2  "no space left on device"

Docker images and volumes live under `C:\ProgramData\DockerDesktop` (or
inside the WSL2 VHDX file). When that disk fills, builds fail.

```powershell
docker system df              # see what's using space
docker system prune -a        # nuke unused images, networks, build cache
docker volume prune           # nuke unused volumes (careful — deletes data)
```

### 4.3  Builds are slow / containers feel laggy

Almost always one of three causes:

1. **Code mounted from the Windows side, not WSL.** See section 2.2 — move
   the repo into WSL or accept slow file watching.
2. **Docker Desktop has too little RAM.** Settings → Resources → bump it.
3. **Antivirus scanning Docker's WSL VHDX.** Add an exclusion for
   `%LOCALAPPDATA%\Docker\wsl\data\*.vhdx`.

### 4.4  "exec /usr/local/bin/uvicorn: no such file or directory" or "bad interpreter: /bin/bash^M"

Line endings got CRLF-ified. Re-clone with `core.autocrlf=input` set
(section 2.1), or normalise manually:

```powershell
git rm --cached -r .
git reset --hard
```

That re-checks out everything respecting `.gitattributes`.

### 4.5  Docker Desktop won't start / "WSL update failed"

Open PowerShell **as Administrator**:

```powershell
wsl --update
wsl --set-default-version 2
```

Restart Docker Desktop.

---

## 5. Migrating state from another machine

If you developed on macOS/Linux and want to bring the populated database,
ingested PDFs, and ChromaDB embeddings to Windows:

### On the source machine

```bash
# From the project root (macOS or Linux)
./scripts/export-state.sh
# Produces: ./cloudsla-state-YYYYMMDD-HHMMSS.tar.gz
```

Copy the resulting `.tar.gz` to the Windows machine (USB / cloud
drive / `scp` — anything).

### On the Windows machine

```powershell
# Stop the stack first so volumes aren't being written to
docker compose down

# Make sure containers exist (they don't have to be running)
docker compose up --no-start

# Run the import (PowerShell needs `bash` from Git for Windows / WSL)
bash ./scripts/import-state.sh ./cloudsla-state-20260623-180000.tar.gz

# Bring everything back up
docker compose up -d
```

The script will:
1. Restore the Postgres dump into the `postgres` container.
2. Copy the ChromaDB collection files into the `chroma_data` volume.
3. Sync the `sla_docs/` PDFs back to the host.

After this, the UI on the Windows machine looks identical to the source
machine — same providers, same ingested SLAs, same embeddings, same
ranking history.

---

## 6. Quick reference card

```powershell
# Start everything
docker compose up --build -d

# Tail api logs
docker compose logs -f api

# Restart just the api (after backend code changes)
docker compose restart api

# Rebuild + restart frontend (after React changes)
docker compose up --build frontend -d

# Stop everything (keep data)
docker compose down

# Stop everything and wipe Postgres + ChromaDB (factory reset)
docker compose down -v

# Run a one-off command inside the api container
docker compose exec api python -c "import sys; print(sys.version)"

# Open a psql shell against the running Postgres
docker compose exec postgres psql -U user -d cloudsla
```

---

## 7. Troubleshooting checklist

If the UI at http://localhost:3000 doesn't load, walk through this in order:

1. `docker compose ps` — are all 8 containers `Up (healthy)`?
2. `docker compose logs -f api` — any Python tracebacks at startup?
3. `curl http://localhost:8000/health` — does the api respond?
4. Check Windows firewall isn't blocking `localhost:3000` (it shouldn't, but corporate AV occasionally does).
5. Hard-reload the browser (Ctrl + Shift + R) — sometimes Vite/React leftover bundles cache.

If you're stuck, share the output of these three commands and the symptom
description:

```powershell
docker compose ps
docker compose logs api --tail 100
docker version
```
