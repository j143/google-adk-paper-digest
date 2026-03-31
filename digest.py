"""5G Research Paper Digest Agent

A SequentialAgent pipeline that takes a research paper (PDF or URL),
extracts sections, summarises key 5G/6G/K8s/AI-infra claims, critiques
feasibility, proposes an action plan, and validates the result.

Usage
-----
    python digest.py <paper.pdf|URL> [--output md]

Local Llama setup (zero-cost)
------------------------------
    ollama serve &
    ollama pull llama3.2:3b
    pip install -r requirements.txt
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import textwrap
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.runners import InMemoryRunner

# ---------------------------------------------------------------------------
# Environment – point to local Ollama (overridable via environment variables)
# ---------------------------------------------------------------------------
os.environ.setdefault("OPENAI_API_KEY", "ollama")
os.environ.setdefault("OPENAI_MODEL_NAME", "llama3.2:3b")
os.environ.setdefault("OPENAI_API_BASE", "http://localhost:11434/v1")

# Model string forwarded to every LlmAgent
_MODEL = os.environ["OPENAI_MODEL_NAME"]

# ---------------------------------------------------------------------------
# Helper tools (called by agents via tool-use)
# ---------------------------------------------------------------------------

def extract_sections(input_url_or_path: str) -> dict[str, str]:
    """Extract abstract, introduction, methods and results from a PDF file or
    a web URL.

    Args:
        input_url_or_path: Local path to a PDF file (must end with ``.pdf``)
            or an HTTP/HTTPS URL pointing to an HTML page or a PDF served
            over the web.

    Returns:
        A dict with keys ``abstract``, ``methods``, and ``results`` whose
        values are the extracted text for the respective section (may be an
        empty string when the section was not detected).
    """
    text = _fetch_text(input_url_or_path)
    return _split_sections(text)


def relevance_5g_check(abstract: str) -> str:
    """Score relevance of a paper abstract to 5G/6G/K8s/AI-infra topics.

    Args:
        abstract: The abstract text of the paper.

    Returns:
        A short human-readable relevance rating string.
    """
    keywords = ["5g", "6g", "ngap", "gnb", "amf", "kubernetes", "sctp", "ooc", "nr"]
    score = sum(1 for kw in keywords if kw in abstract.lower())
    total = len(keywords)
    label = "High" if score > 4 else ("Medium" if score > 2 else "Low")
    return f"Relevance: {score}/{total} – {label}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_text(source: str) -> str:
    """Return raw text from a PDF path or URL."""
    if source.lower().startswith("http://") or source.lower().startswith("https://"):
        response = requests.get(source, timeout=30)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "pdf" in content_type or source.lower().endswith(".pdf"):
            return _extract_pdf_bytes(response.content)
        soup = BeautifulSoup(response.text, "html.parser")
        # Remove script/style noise
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        return soup.get_text(separator="\n")
    # Local PDF
    if source.lower().endswith(".pdf"):
        with open(source, "rb") as fh:
            return _extract_pdf_bytes(fh.read())
    # Assume plain text
    with open(source, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _extract_pdf_bytes(raw: bytes) -> str:
    """Extract text from raw PDF bytes using PyPDF2."""
    import io
    import PyPDF2  # imported lazily so the module works without it for URL mode

    reader = PyPDF2.PdfReader(io.BytesIO(raw))
    pages = reader.pages[:10]  # First 10 pages are usually enough
    return "\n".join(page.extract_text() or "" for page in pages)


def _split_sections(text: str) -> dict[str, str]:
    """Heuristically split paper text into named sections."""
    def _grab(pattern: str, fallback_chars: int = 2000) -> str:
        m = re.search(pattern, text, re.I | re.S)
        if m:
            return m.group(1).strip()[:2000]
        return ""

    abstract = _grab(r"abstract\s*[:\-–]?(.*?)(?:1\.?\s+introduction|keywords)", 2000)
    if not abstract:
        # Fallback: first 800 chars
        abstract = text[:800].strip()

    methods = _grab(
        r"(?:methods?|methodology|implementation|protocol)\s*[:\-–]?(.*?)"
        r"(?:results?|evaluation|experiments?|discussion)",
        2000,
    )
    results = _grab(
        r"(?:results?|evaluation|experiments?)\s*[:\-–]?(.*?)"
        r"(?:conclusion|discussion|related work|references)",
        2000,
    )

    return {"abstract": abstract, "methods": methods, "results": results}


# ---------------------------------------------------------------------------
# Agent definitions
# ---------------------------------------------------------------------------

extractor_agent = LlmAgent(
    name="extractor",
    model=_MODEL,
    instruction=textwrap.dedent("""
        You are a paper extraction specialist.
        The user will provide a research-paper source (PDF path or URL).
        Call the `extract_sections` tool with that source.
        Return the resulting dict as JSON with keys:
        abstract, methods, results.
        Do NOT add extra commentary.
    """),
    tools=[extract_sections],
    output_key="sections",
)

summarizer_agent = LlmAgent(
    name="summarizer",
    model=_MODEL,
    instruction=textwrap.dedent("""
        You are a 5G/6G/AI-infra research summarizer.
        The previous agent stored extracted paper sections in state['sections'].
        Read the abstract, methods, and results from that state.
        Produce 3-5 bullet-point claims most relevant to 5G, 6G, Kubernetes,
        or AI infrastructure. Be concise (≤25 words per bullet).
        Prefix each bullet with "•".
    """),
    output_key="claims",
)

critiquer_agent = LlmAgent(
    name="critiquer",
    model=_MODEL,
    instruction=textwrap.dedent("""
        You are a pragmatic systems engineer who works with Python, Rust, and
        Kubernetes.
        Call `relevance_5g_check` with the abstract from state['sections']['abstract'].
        Then answer two questions in ≤150 words total:
        1. Feasibility: Can the core ideas be implemented in Python/Rust + K8s?
           What are the main gaps or risks?
        2. Verdict: Worth exploring further? (Yes / Partially / No)
    """),
    tools=[relevance_5g_check],
    output_key="critique",
)

actionizer_agent = LlmAgent(
    name="actionizer",
    model=_MODEL,
    instruction=textwrap.dedent("""
        You are a software product manager turning research into action.
        Using state['claims'] and state['critique'], generate:
        1. A GitHub issue title (≤72 chars, starts with a tag like [5G] or [6G]).
        2. A 5-step implementation plan (numbered list, one line each).
        3. A short code stub in Python or Rust illustrating the first step.
        Keep the whole response under 300 words.
    """),
    output_key="action_plan",
)

validator_agent = LlmAgent(
    name="validator",
    model=_MODEL,
    instruction=textwrap.dedent("""
        You are a research quality validator.
        Review state['claims'], state['critique'], and state['action_plan'].
        Output:
        • Novelty score: N/10 with one-sentence justification.
        • Completeness: does the digest cover abstract → claims → critique → action? (Yes/Partial/No)
        • 1-3 suggested arXiv search queries to find related work.
        Keep the response under 120 words.
    """),
    output_key="novelty",
)

# ---------------------------------------------------------------------------
# Sequential pipeline
# ---------------------------------------------------------------------------

digest_chain = SequentialAgent(
    name="paper_digest",
    sub_agents=[extractor_agent, summarizer_agent, critiquer_agent,
                actionizer_agent, validator_agent],
)

# ---------------------------------------------------------------------------
# Runner helpers
# ---------------------------------------------------------------------------

def run_digest(paper_source: str) -> dict[str, Any]:
    """Run the full digest pipeline on *paper_source* and return the state.

    Creates a throwaway in-memory session, feeds *paper_source* to the
    SequentialAgent pipeline, and returns the accumulated session state dict
    (which contains the ``output_key`` values produced by each agent).
    """
    import asyncio
    from google.genai import types as genai_types

    _APP_NAME = "paper_digest"
    _USER_ID = "cli_user"

    runner = InMemoryRunner(agent=digest_chain, app_name=_APP_NAME)

    # Session service is async – create session with asyncio.run.
    session = asyncio.run(
        runner.session_service.create_session(
            app_name=_APP_NAME, user_id=_USER_ID
        )
    )

    content = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=paper_source)],
    )

    # runner.run() is synchronous and streams Event objects.
    # Each event may carry a state_delta in its actions that contains the
    # output_key value produced by the current agent.
    state: dict[str, Any] = {}
    for event in runner.run(
        user_id=_USER_ID,
        session_id=session.id,
        new_message=content,
    ):
        if event.actions and event.actions.state_delta:
            state.update(event.actions.state_delta)

    # Also retrieve the final session state for completeness (some ADK versions
    # persist state only to the session object, not to individual events).
    final_session = asyncio.run(
        runner.session_service.get_session(
            app_name=_APP_NAME, user_id=_USER_ID, session_id=session.id
        )
    )
    if final_session and final_session.state:
        state.update(final_session.state)

    return state


def _format_markdown(state: dict[str, Any], source: str) -> str:
    """Render the digest state as a Markdown research brief."""
    lines = [
        "# 5G Research Paper Digest",
        f"\n**Source:** {source}\n",
        "---",
        "## Key Claims",
        state.get("claims", "_Not generated._"),
        "",
        "## Critique & Feasibility",
        state.get("critique", "_Not generated._"),
        "",
        "## Action Plan",
        state.get("action_plan", "_Not generated._"),
        "",
        "## Validation",
        state.get("novelty", "_Not generated._"),
    ]
    return "\n".join(lines)


def _format_plain(state: dict[str, Any]) -> str:
    """Render the digest state as plain text."""
    keys = ["claims", "critique", "action_plan", "novelty"]
    parts = []
    for k in keys:
        val = state.get(k, "")
        if val:
            parts.append(f"=== {k.upper()} ===\n{val}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="digest",
        description="5G Research Paper Digest Agent – summarize, critique, actionize.",
    )
    parser.add_argument(
        "source",
        help="Path to a PDF file or an HTTP(S) URL of the paper.",
    )
    parser.add_argument(
        "--output",
        choices=["md", "plain"],
        default="plain",
        help="Output format: 'md' for Markdown, 'plain' for plain text (default).",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    print(f"[digest] Processing: {args.source}", file=sys.stderr)
    state = run_digest(args.source)

    if args.output == "md":
        output = _format_markdown(state, args.source)
    else:
        output = _format_plain(state)

    print("\n=== PAPER DIGEST ===\n")
    print(output)


if __name__ == "__main__":
    main()
