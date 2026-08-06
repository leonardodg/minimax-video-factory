# Self-hosted Runner Setup (GPU label)

Esta máquina (máquina com GPU) deve ser registrada como self-hosted runner do GitHub Actions
para rodar o job `gpu-validation` e o CD `build-push`.

## 1. Instalar o runner

```bash
# Criar diretório do runner
mkdir -p ~/actions-runner && cd ~/actions-runner

# Baixar (versão atual — ajustar se necessário)
curl -o actions-runner-linux-x64-2.319.1.tar.gz -L https://github.com/actions/runner/releases/download/v2.319.1/actions-runner-linux-x64-2.319.1.tar.gz
tar xzf actions-runner-linux-x64-2.319.1.tar.gz
```

## 2. Configurar (token do repo)

```bash
# Pegar token em: https://github.com/leonardodg/minimax-video-factory/settings/actions/runners/new
# Ou via CLI:
# gh api repos/leonardodg/minimax-video-factory/actions/runners/registration-token --jq .token
TOKEN=$(gh api repos/leonardodg/minimax-video-factory/actions/runners/registration-token --jq .token)
./config.sh --url https://github.com/leonardodg/minimax-video-factory --token "$TOKEN" --labels "gpu"
```

- **Labels**: digite `gpu` (o workflow CI usa `runs-on: [self-hosted, linux, gpu]`)
- Work folder: `_work` (padrão)

## 3. Instalar como service (auto-start no boot)

```bash
sudo ./svc.sh install
sudo ./svc.sh start
```

## 4. Verificar

```bash
# Status do serviço
sudo ./svc.sh status

# Ver no GitHub
# https://github.com/leonardodg/minimax-video-factory/settings/actions/runners
```

## 5. Pré-requisitos da máquina (já atendidos)

- Docker + docker compose plugin
- nvidia-container-toolkit (`sudo apt install nvidia-container-toolkit && sudo systemctl restart docker`)
- GPU NVIDIA (RTX 4080 12GB) — verificado com `nvidia-smi`
- Modelos em `/var/tmp/minimax/models` (ou `/opt/minimax/models`) — ~32GB
- Container `minimax-comfyui` rodando (o job GPU espera que ele exista; se não, roda `start_comfyui.sh`)

## 6. Testar job GPU local

```bash
cd $PROJECT_ROOT
./scripts/diagnose.sh
```

## 7. CD (build+push) também roda no mesmo runner

O workflow `.github/workflows/publish.yml` usa `runs-on: [self-hosted, linux, gpu]` e chama `scripts/publish_image.sh` que:
- Builda a imagem (usa cache local — rápido)
- Tag + push para Docker Hub (usa `DOCKER_HUB_USER/REPO/TOKEN` secrets)

---

**Resumo dos secrets necessários no GitHub (Settings > Secrets > Actions):**
| Secret | Valor |
|---|---|
| `DOCKER_HUB_USER` | `leodg` |
| `DOCKER_HUB_REPO` | `minimax-video-factory` |
| `DOCKER_HUB_TOKEN` | *Docker Hub Access Token (Read/Write)* |

*O token Docker Hub pode ser criado em https://hub.docker.com/settings/security → New Access Token.*

---

**Arquivos criados:**
- `.github/workflows/ci.yml` — CI cloud (static/unit/handshake) + GPU job self-hosted
- `.github/workflows/publish.yml` — CD build+push self-hosted