# Remote MCP over HTTPS (VPS deployment)

This project can be deployed on a VPS with Docker and expose the MCP server over
**HTTPS**, so OpenCode connects with a plain `type: "remote"` URL — no local uv,
no `docker exec`, no host files. Only the VPS needs Docker + the models.

## Architecture

```
OpenCode ──HTTPS──> Caddy/nginx (TLS, on VPS) ──> docker:127.0.0.1:8848 ──> MCP server (fastmcp streamable-http)
                                                                  └──> ComfyUI 127.0.0.1:8188 (same container)
```

ComfyUI and the MCP server run in the SAME container (shared models + output).

## 1. On the VPS

1. Install Docker + compose plugin + NVIDIA container toolkit (same as local).
2. Put the project on the VPS (git clone or `docker pull` + this repo's compose).
3. Create `.env` from `.env.example`; set at least:

   ```
   MODELS_DIR=/var/tmp/minimax/models
   OUTPUT_DIR=/var/tmp/minimax/output
   MCP_TRANSPORT=streamable-http
   MCP_HOST=0.0.0.0
   MCP_PORT=8848
   COMFYUI_EXTRA_ARGS=--lowvram --fast-disk --disable-pinned-memory
   ```

4. Download models (only needed once):

   ```
   ./scripts/download_models.sh
   ```

5. Start:

   ```
   ./scripts/start_comfyui.sh
   ```

6. Run the MCP HTTP server inside the container (background):

   ```
   docker exec -d minimax-comfyui bash /workspace/scripts/mcp_http_runner.sh
   ```

   Verify locally on the VPS:

   ```
   curl -s http://127.0.0.1:8848/mcp | head -c 200
   ```

   (streamable-http serves the MCP endpoint at `/mcp`; a GET returns the
   `Mcp-Session-Id` + SSE hint — expected.)

## 2. TLS reverse proxy (Caddy — automatic HTTPS)

Install Caddy on the VPS. `Caddyfile`:

```
mcp.example.com {
    reverse_proxy 127.0.0.1:8848
}
```

Or nginx (manual certs):

```
server {
    listen 443 ssl;
    server_name mcp.example.com;
    ssl_certificate     /etc/letsencrypt/live/mcp.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mcp.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8848;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
    }
}
```

> ⚠️ Security: the MCP server has NO auth. The compose file binds the port to
> `127.0.0.1` only — never publish it on `0.0.0.0` publicly. Put Basic Auth or
> mTLS in front of Caddy, or use a Cloudflare tunnel / Tailscale for the HTTPS URL.

## 3. OpenCode config (`opencode.json`)

Remote (HTTPS) — this is the "MCP por link https" you asked about:

```jsonc
{
  "mcp": {
    "minimax-video-factory": {
      "type": "remote",
      "url": "https://mcp.example.com/mcp",
      "enabled": true
    }
  }
}
```

### Local examples — for comparison

**A) stdio via docker exec (no host uv)** — run MCP in the container:

```jsonc
{
  "mcp": {
    "minimax-video-factory": {
      "type": "local",
      "command": [
        "docker", "exec", "-i", "minimax-comfyui",
        "bash", "/workspace/scripts/mcp_runner.sh"
      ],
      "enabled": true
    }
  }
}
```

**B) stdio via uv (host uv required)** — classic setup:

```jsonc
{
  "mcp": {
    "minimax-video-factory": {
      "type": "local",
      "command": [
        "uv", "run", "--directory", "/path/to/minimax-video-factory",
        "python", "src/minimax_mcp/server.py"
      ],
      "environment": {
        "MODELS_DIR": "/opt/minimax/models",
        "COMFYUI_URL": "http://127.0.0.1:8188",
        "OUTPUT_DIR": "/path/to/minimax-video-factory/output"
      },
      "enabled": true
    }
  }
}
```

## 4. Path reporting on the VPS

When running in the container, the MCP server reports output paths via
`OUTPUT_HOST_DIR` (the host view of the output mount), so `wait_for_video` /
`compose_final` return paths valid on the VPS. `compose_final` maps inputs back
into the container for ffmpeg. If OpenCode runs on a different machine than the
VPS, copy the produced `.mp4` (e.g. `scp`/`rsync`) or mount output over NFS.
