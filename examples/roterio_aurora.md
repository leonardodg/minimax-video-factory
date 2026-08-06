# Example Script — "Aurora" (12s concept, 2 scenes)

> Teste real do fluxo OpenCode → MCP → ComfyUI (MiniMax H3).
> Cada cena gera vídeo + áudio estéreo nativo; `compose_final` junta tudo.

## Scene 1 (0–6s) — "Despertar do oceano"

Close-up macro sobre a superfície do oceano ao amanhecer. Gotas de água salgada
levantam em câmera lenta e congelam no ar enquanto a primeira luz dourada
atravessa a névoa. Som ambiente de mar em calmaria, ondas suaves e a primeira
nota de um celesta distante.

**H3 prompt:**
```
Extreme macro shot of the ocean surface at sunrise. Slow-motion saltwater
droplets lift and freeze mid-air as golden first light pierces the mist.
Shallow depth of field, sun glint bokeh, 24fps film look. Ambient audio: calm
ocean waves, soft lapping, a distant celesta note rising.
```

## Scene 2 (6–12s) — "Aurora sobre a cordilheira"

Paisagem ampla: uma cordilheira coberta de neve sob uma aurora boreal verde que
ondula lentamente. Estrelas visíveis no topo, vento leve movendo a neve em
espiral. O som vai crescendo: vento, baixo profundo e harmônicos suaves.

**H3 prompt:**
```
Wide landscape of a snow-covered mountain range under a slowly rippling green
aurora borealis. Stars visible above, light wind spiraling fresh snow across
the ridge. Audio swells: strong wind, deep bass, soft rising harmonics.
```

## Final

`compose_final([scene1.mp4, scene2.mp4], output/aurora_final.mp4)`
