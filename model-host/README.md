# Applaut AI model host

The in-house model runs on its own Oracle VM. The app VM (`lvamo-backend`)
keeps everything else: the database, the API, and the `ai-worker` that sends
the model one job at a time. Only prompts and answers cross between the two:
a job posting plus the user's master profile goes over, scoring facts or three
written paragraphs come back. The model VM stores nothing.

```
app VM (lvamo-backend)                     model VM
  ai-worker ──HTTP + API key──▶ WireGuard ──▶ llm (llama-server, 10.8.0.2:8080)
  10.8.0.1                    UDP 51820
```

Not deployed yet (2026-10-31): this waits for the model VM. Until then the
same server runs on the app VM as the `llm-bench` test container.

## 1. Model VM

Ampere A1.Flex, 4 OCPU / 24 GB, Ubuntu 24.04 aarch64, 50 GB boot volume.

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 wireguard
sudo usermod -aG docker ubuntu   # log out and back in
```

## 2. WireGuard

On each VM:

```bash
wg genkey | sudo tee /etc/wireguard/private.key | wg pubkey | sudo tee /etc/wireguard/public.key
sudo chmod 600 /etc/wireguard/private.key
```

Model VM, `/etc/wireguard/wg0.conf`:

```ini
[Interface]
Address = 10.8.0.2/24
ListenPort = 51820
PrivateKey = <model VM private.key>

[Peer]
PublicKey = <app VM public.key>
AllowedIPs = 10.8.0.1/32
```

App VM, `/etc/wireguard/wg0.conf`:

```ini
[Interface]
Address = 10.8.0.1/24
PrivateKey = <app VM private.key>

[Peer]
PublicKey = <model VM public.key>
Endpoint = <model VM public IP>:51820
AllowedIPs = 10.8.0.2/32
PersistentKeepalive = 25
```

Firewalls on the model VM:
- OCI security list: ingress UDP 51820 from the app VM's public IP
  (130.61.106.172/32) only. Nothing else beyond SSH.
- Ubuntu's own iptables rejects inbound traffic by default. Allow WireGuard:
  `sudo iptables -I INPUT 5 -p udp --dport 51820 -s 130.61.106.172 -j ACCEPT && sudo netfilter-persistent save`

Then on both: `sudo systemctl enable --now wg-quick@wg0`, and from the app
VM `ping 10.8.0.2`.

## 3. The model

```bash
git clone https://github.com/vsvedantham/lvamo.git && cd lvamo/model-host
mkdir -p models
curl -L -o models/Qwen3.5-9B-Q4_0.gguf <the Q4_0 GGUF chosen in Phase 0, see the design doc §10>
cp .env.example .env    # set LLAMA_API_KEY: openssl rand -hex 32
docker compose up -d
curl -s -H "Authorization: Bearer $(grep ^LLAMA_API_KEY .env | cut -d= -f2)" http://10.8.0.2:8080/v1/models
```

Use a Q4_0 file, not Q4_K_M: on these Neoverse-N1 cores llama.cpp repacks
Q4_0 for ARM and reads prompts about twice as fast.

## 4. The app VM

In `.env.production`:

```
APPLAUT_LLM_BASE_URL=http://10.8.0.2:8080/v1
APPLAUT_LLM_API_KEY=<the same LLAMA_API_KEY>
APPLAUT_LLM_MODEL=qwen3.5-9b-q4_0
APPLAUT_AI_ALLOWLIST=<emails allowed to choose Applaut AI>
```

then `docker compose -f docker-compose.prod.yml up -d ai-worker`. The worker
logs each item (`docker compose -f docker-compose.prod.yml logs -f ai-worker`).
If the model VM is down, items fail, go to the back of the queue, and fail for
good after 3 tries; the job shows the error.

## Before real users' data goes over

The model VM belongs to another person's Oracle account, so user profiles and
CVs are processed on infrastructure LVAMO doesn't own. Settle this first: a
written processing agreement with the VM's owner, and a line in the privacy
notice naming the processor.
