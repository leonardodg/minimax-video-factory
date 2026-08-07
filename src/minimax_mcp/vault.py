"""Optional, best-effort markdown export of knowledge base documents to Obsidian."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _slugify(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.lower()).strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug[:60] or "sem-titulo"


def write_markdown_copy(document: dict[str, Any], vault_path: str | Path | None) -> dict[str, Any]:
    """Write a readable .md copy of `document` under `<vault_path>/Knowledge/`.

    Never raises and never returns ok=False: a broken/missing vault must not
    block ingestion, which already succeeded in Postgres by the time this runs.
    """
    if not vault_path:
        return {"ok": True, "skipped": True, "reason": "VAULT_PATH not configured"}
    try:
        folder = Path(vault_path) / "Knowledge"
        folder.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        slug = _slugify(document.get("title") or f"documento-{document.get('id')}")
        filepath = folder / f"{date_str}-{slug}.md"

        tags = document.get("tags") or []
        tags_line = " ".join(f"#{t}" for t in tags)

        content = (
            "---\n"
            f"source_url: {document.get('source_url') or ''}\n"
            f"platform: {document.get('platform') or ''}\n"
            f"type: {document.get('type') or ''}\n"
            f"created_at: {date_str}\n"
            "---\n\n"
            f"# {document.get('title') or slug}\n\n"
            f"{tags_line}\n\n"
            f"## Resumo\n\n{document.get('summary') or ''}\n\n"
            f"## Tutorial\n\n{document.get('tutorial') or ''}\n\n"
            f"## Transcrição completa\n\n{document.get('transcription_text') or ''}\n"
        )
        filepath.write_text(content, encoding="utf-8")
        return {"ok": True, "skipped": False, "path": str(filepath)}
    except Exception as e:
        logger.warning("Vault markdown copy failed (non-blocking): %s", e)
        return {"ok": True, "skipped": True, "reason": str(e)}
