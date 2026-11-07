# Applaut AI model hosts

The in-house models run on model hosts: Oracle VMs that do nothing else. The
app VM (`lvamo-backend`) keeps everything else: the database, the API, and the
`ai-worker`, which runs one lane per model host and sends each host one job at
a time, in queue order. Only prompts and answers cross between them: a job
posting plus the user's master profile goes over, scoring facts or written
text comes back. A model host stores nothing.

```
app VM (lvamo-backend, 10.8.0.1)                     model hosts (all identical)
  ai-worker                                          ┌ 10.8.0.2 ───────────────┐
    lane 10.8.0.2 ──HTTP + API key── WireGuard ────▶ │ scorer :8080  writer :8081 │
    lane 10.8.0.3 ──────────────────────────────┐    └──────────────────────────┘
                                                └──▶ ┌ 10.8.0.3 (later) ───────┐
APPLAUT_MODEL_HOSTS=10.8.0.2,10.8.0.3                │ scorer :8080  writer :8081 │
                                                     └──────────────────────────┘
```

Every host runs both task models: the **scorer** (reads a posting into facts)
on :8080 and the **writer** (CV headline and bullets, cover-letter paragraphs)
on :8081. Which model each one runs is pinned, with checksums, in
[`backend/app/applaut/ai/models.lock`](../backend/app/applaut/ai/models.lock).
A lane uses its host only while both ports report exactly those models, so a
job scored on one host means the same as one scored on another.

## On the app VM (2026-11-07, until a separate model host exists)

Applaut AI went live with its one model host on the app VM itself, on cores
1–3, using [`docker-compose.app-vm.yml`](docker-compose.app-vm.yml): no
WireGuard; the servers join the app's Docker network as `model-host` and
publish only on 127.0.0.1. In `/home/ubuntu/lvamo/model-host/.env`:
`COMPOSE_FILE=docker-compose.app-vm.yml`, `WG_ADDRESS=127.0.0.1`,
`LLAMA_CPUS=1-3`, `LLAMA_THREADS=3`, `LLAMA_API_KEY=…` (the same as
`APPLAUT_LLM_API_KEY`). In `.env.production`: `APPLAUT_MODEL_HOSTS=model-host`.
Start the app stack first (the network must exist), then `./update.sh --no-pull`.
When a separate host is added, stop this one (`docker compose down` here) and
replace `model-host` in `APPLAUT_MODEL_HOSTS` with its WireGuard address.

## Add a model host

1. **The VM.** Ampere A1.Flex, 4 OCPU / 24 GB, Ubuntu 24.04 aarch64, 50 GB
   boot volume. OCI security list: ingress UDP 51820 from the app VM's public
   IP (130.61.106.172/32) only, nothing else beyond SSH.
2. **On the new VM**, with the next free WireGuard address (10.8.0.2, .3, …):

   ```bash
   git clone https://github.com/vsvedantham/lvamo.git && cd lvamo/model-host
   LLAMA_API_KEY=<APPLAUT_LLM_API_KEY from the app VM> ./setup.sh 10.8.0.3 '<app VM WireGuard public key>' 130.61.106.172
   ```

   It installs Docker and WireGuard, makes the VM a WireGuard peer of the app
   VM, downloads the pinned models (about 5 GB each, checksums verified),
   starts both servers, and prints the `[Peer]` block for the app VM.
3. **On the app VM**: add that `[Peer]` block to `/etc/wireguard/wg0.conf`,
   `sudo systemctl restart wg-quick@wg0`, `ping 10.8.0.3`. Append the address
   to `APPLAUT_MODEL_HOSTS` in `.env.production`, then
   `docker compose -f docker-compose.prod.yml up -d ai-worker`.
4. **Check**: `docker compose -f docker-compose.prod.yml logs ai-worker` shows
   "Serving the AI queue on N model host(s)" and no "Host not usable" for the
   new address.

The app VM's own WireGuard setup (once): `wg genkey | sudo tee
/etc/wireguard/private.key | wg pubkey`, and `/etc/wireguard/wg0.conf` with
`[Interface] Address = 10.8.0.1/24` and its private key; each host adds a
`[Peer]`.

## Change a model

Edit `models.lock` (file, checksum, URL from the model's Hugging Face page,
pinned to a commit), merge, then on **every** host `./update.sh` (pulls,
downloads, verifies, restarts, prints what each port serves), then restart
`ai-worker`. Hosts that still run the old model are left out by their lane
until they're updated. Use Q4_0 files: on these Neoverse-N1 cores llama.cpp
repacks Q4_0 for ARM and reads prompts about twice as fast as Q4_K_M.

## When a host goes down

Its lane puts the job it was doing back in its place in the queue, without
using one of the job's 3 tries, and checks the host again after 30 s, 1, 2,
then every 5 minutes. The other hosts carry on with the queue. Only real
model errors (an unusable answer, text that breaks the rules twice) count as
tries.

## Capacity

About 10 Applaut AI users per host on a normal night (v2 plan §3, B5: writing
with reworded bullets takes ~6.5 min a set). The
Settings card stops offering Applaut AI to allow-listed users once
`APPLAUT_AI_USERS_PER_HOST` × hosts users have it.

## Before real users' data goes over

Each model host belongs to another person's Oracle account, so user profiles
and CVs are processed on infrastructure LVAMO doesn't own. Settle this first,
per host owner: a written processing agreement, and a line in the privacy
notice naming the processor. Also check the account is Pay As You Go (Oracle
reclaims idle Always Free VMs, and a host busy only at night can look idle).
