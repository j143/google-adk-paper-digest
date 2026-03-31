# 5G Research Paper Digest Agent

A zero-cost, locally-runnable **SequentialAgent** pipeline built with
[Google ADK](https://github.com/google/adk-docs) that turns a 5G/6G/K8s/AI-infra
research paper (PDF file **or** URL) into a one-page "research brief" with:

* **Extracted sections** – abstract, methods, results
* **Key claims** – 3-5 bullets most relevant to 5G/6G/Kubernetes/AI infra
* **Feasibility critique** – can I implement this in Python/Rust + K8s?
* **Action plan** – GitHub issue title + 5-step plan + code stub
* **Validation** – novelty score, completeness check, suggested arXiv queries

```
┌──────────────────────────────────────────────────────┐
│  PDF / URL                                           │
│     │                                                │
│  Extractor  ──►  Summarizer  ──►  Critiquer          │
│                                      │               │
│                        Actionizer  ◄─┘               │
│                              │                       │
│                          Validator                   │
│                              │                       │
│                      Research Brief                  │
└──────────────────────────────────────────────────────┘
```

## Quick start

### 1 – Local Llama setup (zero-cost)

```bash
# Install and start Ollama
ollama serve &
ollama pull llama3.2:3b

# Install Python dependencies
pip install -r requirements.txt
```

### 2 – Run on a paper

```bash
# From a URL
python digest.py https://arxiv.org/pdf/2503.12345.pdf

# From a local PDF
python digest.py my_paper.pdf

# Markdown output (one-page research brief)
python digest.py my_paper.pdf --output md
```

### 3 – Docker (one-file app)

```bash
# Build
docker build -t paper-digest .

# Run (mount a local PDF)
docker run --rm \
  -v "$(pwd)":/papers \
  -e OPENAI_API_BASE=http://host.docker.internal:11434/v1 \
  paper-digest /papers/my_paper.pdf --output md
```

## Pipeline stages

| Stage | Agent | What it does |
|-------|-------|--------------|
| 1 | **Extractor** | Calls `extract_sections` tool → returns abstract / methods / results |
| 2 | **Summarizer** | 3-5 bullet claims relevant to 5G/6G/K8s/AI infra |
| 3 | **Critiquer** | Calls `relevance_5g_check` tool → feasibility verdict |
| 4 | **Actionizer** | GitHub issue title + 5-step plan + code stub |
| 5 | **Validator** | Novelty score (1-10) + completeness + arXiv search queries |

## Example output

```
=== CLAIMS ===
• Novel 6G OOC protocol reduces latency 40 % via SCTP tweaks
• K8s-native deployment for gNB edge with FluxCD reconciliation
• AMF handoff latency below 5 ms under simulated 10 k UE load

=== CRITIQUE ===
Relevance: 7/9 – High
Feasible in Rust + FluxCD, but requires real NGAP test harness.
Verdict: Yes – worth prototyping for a 6G repo.

=== ACTION_PLAN ===
Title: [6G] Implement OOC protocol from arXiv:2503.12345
1. Stand up a minimal SCTP echo server in Rust (tokio-sctp).
2. Implement OOC packet framing per §3.2 of the paper.
3. Write a K8s DaemonSet manifest for gNB edge nodes.
4. Add Prometheus metrics for latency percentiles.
5. Run against a softmodem (OAI/srsRAN) in a kind cluster.
Code stub:
```rust
async fn ooc_packet(conn: &mut SctpStream, payload: &[u8]) {
    conn.send(payload, 0).await.unwrap();
}
```

=== NOVELTY ===
Novelty: 8/10 – novel OOC framing, incremental SCTP work.
Completeness: Yes
arXiv queries: "6G OOC SCTP latency", "gNB K8s edge deployment", "NGAP AMF handoff"
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | `ollama` | API key (any string for Ollama) |
| `OPENAI_MODEL_NAME` | `llama3.2:3b` | Model name passed to Ollama |
| `OPENAI_API_BASE` | `http://localhost:11434/v1` | Ollama OpenAI-compatible endpoint |

## Project structure

```
.
├── digest.py        # SequentialAgent pipeline + CLI
├── requirements.txt # Python dependencies
├── Dockerfile       # One-file Docker app
└── README.md
```

## Your twist ideas

* **Feed BIFOLD papers** – `python digest.py https://bifold.berlin/...`
* **Auto-PR** – pipe `--output md` to a GitHub Actions step that opens a PR
  with the brief in `docs/briefs/`.
* **VLSI-AI papers** – change keywords in `relevance_5g_check` to target
  your domain.
