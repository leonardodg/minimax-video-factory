"""Operational knowledge the AST cannot see.

A tool signature says a parameter is an int with a default. It does not say
that raising it OOMs the card, that an error message means "close your
browser", or that a slow tool needs a two-call workaround. That knowledge was
learned by using the thing, and it lives here.

Every field is optional: a tool with no entry still generates a valid command,
just a drier one.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExtraParam:
    """A parameter the command accepts but the tool itself does not.

    `/minimax-download` takes `transcrever`, `model_size` and `language`
    because it chains into `transcribe_video`. Without this the absorbed
    command would lose half its interface.
    """

    descricao: str
    default: str | None = None


@dataclass(frozen=True)
class Override:
    resumo: str = ""
    # A param_nota REPLACES the English Field(description=...), it does not
    # append to it: the tool API is documented in English, the commands are
    # written in Portuguese, and appending produced bilingual duplicated lines.
    param_notas: Mapping[str, str] = field(default_factory=dict)
    params_extra: Mapping[str, ExtraParam] = field(default_factory=dict)
    passos: tuple[str, ...] = ()


OVERRIDES: dict[str, Override] = {
    # ---------------------------------------------------------------- video
    "download_video": Override(
        resumo=(
            "Baixa um vídeo (Instagram Reel, YouTube) via MCP yt-dlp, "
            "opcionalmente transcreve com Whisper"
        ),
        param_notas={
            "url": "URL do vídeo — Instagram Reel, YouTube, etc",
            "browser": (
                "navegador de onde ler os cookies (chrome, firefox, edge, brave). "
                'Se der erro de "database locked", oriente a fechar o navegador'
            ),
        },
        # This command chains into transcribe_video, so it accepts parameters
        # that download_video itself does not have.
        params_extra={
            "transcrever": ExtraParam(
                "flag — se presente, transcreva o vídeo baixado com Whisper"
            ),
            "model_size": ExtraParam(
                "tiny/base/small/medium/large-v3, se for transcrever", default="small"
            ),
            "language": ExtraParam(
                "código do idioma, se for transcrever", default="pt"
            ),
        },
        passos=(
            "Reporte o arquivo salvo (dir `downloads/`), título, duração e uploader.",
            ("Se `transcrever` foi pedido, chame `transcribe_video` com o caminho "
            "baixado (GPU, `device=cuda`) e reporte o texto + segmentos com "
            "timestamps. Alternativamente, o usuário pode usar o comando dedicado "
            "`/minimax-transcrever <arquivo>` depois."),
            "Não gere vídeo a menos que o usuário peça explicitamente.",
        ),
    ),
    "transcribe_video": Override(
        resumo="Transcreve um vídeo local com Whisper (faster-whisper, GPU)",
        param_notas={
            "video_path": (
                "caminho do arquivo .mp4/.mkv/.webm (aceita path do host, ex.: "
                "`downloads/Video.mp4`); se vier relativo, assuma relativo ao "
                "diretório do projeto (`$PROJECT_ROOT`)"
            ),
            "model_size": "modelo Whisper: tiny/base/small/medium/large-v3",
            "device": "`cuda` (GPU) ou `cpu`",
            "language": "código do idioma (pt, en, es, ...)",
        },
        passos=(
            "Reporte o texto transcrito + segmentos com timestamps + idioma detectado.",
            "Não gere vídeo nem crie prompt a menos que o usuário peça.",
        ),
    ),
    "generate_video": Override(
        resumo="Gera um vídeo no MiniMax H3 (texto→vídeo com áudio nativo estéreo) via MCP",
        param_notas={
            "prompt": (
                "descrição cinematográfica/estruturada do vídeo "
                "(shots, câmera, iluminação, áudio)"
            ),
            "duration": "duração do clipe, 4-15s; o servidor arredonda para a grade de 17 frames",
            "seed": "semente aleatória (inteiro); omita para aleatório",
            "filename_prefix": "prefixo do arquivo de saída",
            "width": (
                "não suba de 1024 — 1344x768 dá OOM no sampler com 12 GB VRAM "
                "(`torch.OutOfMemoryError`). 512x320 é o mais rápido (~5 min)"
            ),
            "height": "não suba de 576 pelo mesmo motivo de VRAM",
        },
        passos=(
            ("Se `prompt` vier em PT, traduza para uma descrição visual EN rica "
            "antes de chamar a tool."),
            ("Aguarde o render completar (5-20 min; use `wait_for_video` se a tool "
            "retornar só o prompt_id). Reporte o caminho final do vídeo (host, via "
            "`OUTPUT_HOST_DIR`) e o prompt_id."),
            "Se houver erro de OOM, reduza para 512x320 e tente novamente.",
            (
                "A tool espera até `wait_seconds` (default 240s). Se o render não "
                "terminar nesse prazo ela devolve `state=rendering` com o "
                "`prompt_id` — isso não é erro. Colete com `/minimax-wait "
                "<prompt_id>` ou acompanhe com `/minimax-fila`."
            ),
        ),
    ),
    "submit_scene": Override(
        resumo="Enfileira uma cena no ComfyUI e devolve o prompt_id, sem esperar o render",
        param_notas={
            "prompt": "prompt estruturado do MiniMax H3 (shots + câmera + áudio)",
            "duration": "duração do clipe, 4-15s; arredonda para a grade de 17 frames",
            "width": "largura (múltiplo de 32); não suba de 1024 — OOM no sampler com 12 GB VRAM",
            "height": "altura (múltiplo de 32); não suba de 576 pelo mesmo motivo de VRAM",
            "seed": "semente aleatória (inteiro); omita para aleatório",
            "filename_prefix": "prefixo do arquivo de saída",
        },
        passos=(
            ("Reporte o `prompt_id`. O render NÃO terminou: use "
            "`/minimax-wait <prompt_id>` para aguardar, ou `/minimax-status "
            "<prompt_id>` para checar sem bloquear."),
        ),
    ),
    "wait_for_video": Override(
        resumo="Bloqueia até um render terminar e devolve o caminho do .mp4",
        param_notas={
            "prompt_id": "o id devolvido por `/minimax-submit-scene`",
            "timeout": "segundos máximos de espera; renders de 1024x576 levam 5-20 min",
        },
        passos=(
            ("Este comando BLOQUEIA. Se o usuário só quer saber o estado agora, "
            "use `/minimax-status` em vez deste."),
        ),
    ),
    "queue_status": Override(
        resumo="Mostra a fila de renderização com barra de progresso",
        param_notas={
            "watch_seconds": (
                "quanto tempo ouvir o progresso. Um step em 1024x576 leva dezenas "
                "de segundos, então uma janela curta pode não capturar nada — use 0 "
                "para pular e ver só a fila"
            ),
        },
        passos=(
            "Mostre o campo `summary`, que já vem formatado para leitura humana.",
            (
                "A porcentagem conta apenas os steps do sampler. O decode do VAE e a "
                "codificação do vídeo vêm depois e não aparecem — não anuncie 100% do "
                "sampler como vídeo pronto."
            ),
            (
                "Se a fila tiver itens que o usuário não submeteu, avise: podem ser "
                "sobras de runs de CI cancelados, que já entupiram a fila antes."
            ),
        ),
    ),
    "get_status": Override(
        resumo="Checa o estado de um render já submetido, sem bloquear",
        param_notas={"prompt_id": "o id devolvido por `/minimax-submit-scene`"},
        passos=(
            ("Reporte o estado (`queued`, `running`, `completed`, `error`) e, se "
            "completo, o caminho do arquivo."),
        ),
    ),
    "health_check": Override(
        resumo="Verifica o ComfyUI e a presença dos modelos MiniMax H3",
        passos=(
            ("Rode isto ANTES de um render longo: descobrir que falta um modelo "
            "depois de 20 minutos de espera é o desperdício que este comando evita."),
            "Se algum modelo estiver ausente, aponte `scripts/download_models.sh`.",
        ),
    ),
    "list_outputs": Override(
        resumo="Lista os vídeos .mp4 já gerados, do mais recente para o mais antigo",
    ),
    "compose_final": Override(
        resumo="Concatena cenas .mp4 em um vídeo final com ffmpeg",
        param_notas={
            "scene_paths": (
                "lista ordenada de arquivos .mp4 — a ordem é a ordem em que as "
                "cenas aparecem no vídeo final"
            ),
            "output_path": "onde escrever o vídeo composto",
        },
        passos=("São necessárias ao menos 2 cenas; com menos, a tool recusa.",),
    ),
    "create_cinematic_prompt": Override(
        resumo="Converte uma transcrição em um prompt estruturado do MiniMax H3",
        param_notas={
            "transcription": "texto completo da transcrição do vídeo",
            "style": "cinematic, educational ou social",
        },
        passos=(
            ("Isto só monta o prompt — não gera vídeo. Para gerar, passe o "
            "resultado para `/minimax-gerar-video`."),
        ),
    ),
    "studio_pipeline": Override(
        resumo="Pipeline completo: URL → download → transcrição → prompt → vídeo",
        param_notas={
            "url": "URL do vídeo de origem — Instagram Reel, YouTube, etc",
            "style": "cinematic, educational ou social",
            "duration": "duração do clipe gerado, em segundos",
            "width": "largura; não suba de 1024 — OOM no sampler com 12 GB VRAM",
            "height": "altura; não suba de 576 pelo mesmo motivo de VRAM",
        },
        passos=(
            ("É o mais demorado de todos (download + Whisper + render). Avise o "
            "usuário antes de começar."),
            "Reporte cada etapa conforme concluir, não só o resultado final.",
        ),
    ),
    # ------------------------------------------------------------------- kb
    "knowledge_ingest_text": Override(
        resumo="Resume e documenta um texto na base de conhecimento com a IA local",
        passos=("Reporte o `document_id`, o título e as tags geradas.",),
    ),
    "knowledge_ingest_markdown": Override(
        resumo="Importa arquivos markdown (ex.: Obsidian) para a base de conhecimento",
        param_notas={
            "path": (
                "arquivo .md ou diretório; diretórios com ponto (.obsidian, .trash) "
                "são ignorados"
            ),
            "recursive": (
                "cuidado ao apontar para um vault inteiro — pode ser milhares de arquivos"
            ),
        },
        passos=(
            ("Quando a nota já tem uma seção `## Summary`, esse texto é "
            "reaproveitado e o LLM é pulado — é o que torna a importação em massa "
            "viável (minutos em vez de horas)."),
            "Reporte quantos arquivos foram importados de quantos encontrados.",
        ),
    ),
    "knowledge_ingest_video": Override(
        resumo="Baixa, transcreve e documenta um vídeo na base de conhecimento",
        passos=("Leva minutos: download + Whisper + LLM. Avise o usuário.",),
    ),
    "knowledge_ingest_audio": Override(
        resumo="Transcreve e documenta um áudio/podcast na base de conhecimento",
        param_notas={
            "path_or_url": "caminho local OU URL; se for URL, baixa antes de transcrever",
        },
    ),
    "knowledge_search": Override(
        resumo="Busca na base de conhecimento (palavra-chave + semântica)",
        passos=(
            ("Reporte título, trechos e URL de origem de cada resultado, para o "
            "usuário conseguir voltar à fonte."),
        ),
    ),
    "knowledge_ask": Override(
        resumo="Responde uma pergunta usando RAG sobre a base de conhecimento",
        passos=(
            ("A resposta vem APENAS da base. Se ela disser que não sabe, isso é o "
            "comportamento correto — não complete com conhecimento próprio."),
            "Sempre mostre as fontes junto da resposta.",
        ),
    ),
    "knowledge_reindex": Override(
        resumo="Recalcula chunks e embeddings de todos os documentos da base",
        param_notas={"embedding_model": "default: EMBEDDING_MODEL do .env"},
        passos=(
            ("Rode depois de trocar o modelo de embedding: vetores antigos não são "
            "comparáveis com os novos, e a busca degrada em silêncio até reindexar."),
            "Percorre a base inteira — pode demorar proporcionalmente ao tamanho dela.",
        ),
    ),
}
