# Graph Report - meu-backend  (2026-05-02)

## Corpus Check
- 2 files · ~692 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 10 nodes · 9 edges · 3 communities detected
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]

## God Nodes (most connected - your core abstractions)
1. `_load_env()` - 2 edges
2. `gerar_resposta_ia()` - 2 edges
3. `handle_text()` - 2 edges
4. `Lead` - 2 edges
5. `Best-effort .env loader sem dependências extras.` - 1 edges

## Surprising Connections (you probably didn't know these)
- None detected - all connections are within the same source files.

## Communities

### Community 0 - "Community 0"
Cohesion: 0.4
Nodes (2): BaseModel, Lead

### Community 1 - "Community 1"
Cohesion: 1.0
Nodes (2): gerar_resposta_ia(), handle_text()

### Community 2 - "Community 2"
Cohesion: 1.0
Nodes (2): _load_env(), Best-effort .env loader sem dependências extras.

## Knowledge Gaps
- **1 isolated node(s):** `Best-effort .env loader sem dependências extras.`
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 0`** (5 nodes): `BaseModel`, `main.py`, `create_lead()`, `health_check()`, `Lead`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 1`** (3 nodes): `bot_telegram.py`, `gerar_resposta_ia()`, `handle_text()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 2`** (2 nodes): `_load_env()`, `Best-effort .env loader sem dependências extras.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_load_env()` connect `Community 2` to `Community 1`?**
  _High betweenness centrality (0.083) - this node is a cross-community bridge._
- **What connects `Best-effort .env loader sem dependências extras.` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._