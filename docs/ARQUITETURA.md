# Arquitetura — minimax-video-factory

Três leituras do mesmo sistema: o que existe (estrutura), com que é feito
(stack) e como um clipe é gerado (fluxo). Detalhes operacionais em
[ARCHITECTURE.md](ARCHITECTURE.md).

## Estrutura

```mermaid
graph TD
  subgraph repo["src/minimax_mcp/"]
    server["server.py — FastMCP, 12 tools"]
    core["core.py — injeção do workflow, submit, resolução da saída"]
    client["comfyui_client.py — HTTP + WS (guards → ComfyUITimeout)"]
    gpu["gpu_lock.py — 1 render por vez"]
    orch["orchestrator.py — studio pipeline"]
    dl["downloader.py — yt-dlp (cookies do navegador)"]
    tr["transcriber.py — faster-whisper"]
  end

  subgraph docker["docker/"]
    img["minimax-comfyui:local — ComfyUI v0.39.1 + /opt/mcp-venv"]
    mcps["serviço mcp — streamable-http :8848"]
  end

  wf["workflows/minimax_h3_t2v_api.json — grafo H3 (14 nós)"]

  oc["OpenCode / Claude Code"] -->|"MCP stdio / http"| server
  oc -->|"docker exec"| img
  server --> core
  core --> wf
  core --> client
  client -->|"POST /prompt · WS /ws · GET /history|/view"| img
  gpu -.->|"trava entre processos"| img
  server --> orch
  orch --> dl
  orch --> tr
  img --> out["output/*.mp4 — vídeo + áudio estéreo"]
```

## Stack

```mermaid
graph LR
  subgraph host[Host]
    uv["Python ≥ 3.11 (host 3.14) + uv"]
    fm["fastmcp 4.0.11"]
    av["av==18.1.0 + faster-whisper"]
    yt["yt-dlp"]
    pb["ruff · pyright · pytest"]
  end

  docker["Docker + nvidia runtime"] --> comfy["ComfyUI v0.39.1 · torch 2.8 DynamicVRAM (--lowvram)"]
  comfy --> h3["MiniMax H3 INT8 ConvRot — fl2va / ref2va (~21 GB cada)"]
  comfy --> loras["LoRA turbo (passo 6) + embeddings"]
  uv --> fm --> mcp["MCP :8848 / stdio"]
  uv --> av --> st["studio: download → transcrição → prompt"]
  uv --> yt
  uv --> pb
  gpu["GPU serializada — RTX 4080, 12 GB"] --> comfy
```

## Fluxo

```mermaid
sequenceDiagram
  participant U as OpenCode
  participant M as MCP server
  participant C as ComfyUI :8188
  U->>M: generate_video / submit_scene
  M->>C: POST /prompt (workflow H3 injetado)
  C-->>M: prompt_id / progresso (WS, fallback HTTP)
  M->>C: GET /history + GET /view
  C-->>M: output/*.mp4 (vídeo + áudio estéreo)
  M-->>U: caminho do .mp4 (ou state=rendering + prompt_id)
```
