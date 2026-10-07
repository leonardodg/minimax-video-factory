# MiniMax Video Factory

Local "video factory" MCP server: MiniMax H3 text-to-video generation, plus
an Audiovisual Studio that downloads a reference video (Instagram/YouTube),
transcribes it locally with Whisper, and turns the transcript into a
cinematic prompt.

> The personal knowledge base (Postgres + pgvector + local LLM) that used to
> live here moved whole — code and production data — to
> [`insta_kb`](https://github.com/leonardodg/insta_kb) in 2026-10-06.

- **New here?** Start with the [MCP Tools Reference](MCP_TOOLS.md) for the
  full list of available tools, or the [Installation](INSTALLATION.md) guide
  to get the stack running.
- **Building or contributing?** See the
  [Developer Docs](dev/index.md) — development environment, module guide,
  extending the system, and testing workflow.
- **Where this is headed:** see the [Roadmap](ROADMAP.md).
- **Code-level reference:** see the [API Reference](api.md), generated
  directly from the source docstrings.
