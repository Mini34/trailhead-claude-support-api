from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

WORD_RE = re.compile(r"[a-z0-9]+")
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "can",
    "do",
    "for",
    "from",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "with",
    "you",
}
QUERY_EXPANSIONS = {
    "arrive": {"delivery", "shipping", "tracking", "estimated"},
    "arrives": {"delivery", "shipping", "tracking", "estimated"},
    "arrival": {"delivery", "shipping", "tracking", "estimated"},
    "eta": {"delivery", "shipping", "tracking", "estimated"},
    "late": {"delayed", "delivery", "shipping", "tracking"},
    "package": {"shipment", "shipping", "tracking", "delivery"},
    "cancel": {"cancellation", "processing", "order"},
    "change": {"edit", "cancellation", "order"},
    "charged": {"billing", "payment", "authorization"},
    "charge": {"billing", "payment", "authorization"},
    "refund": {"return", "payment", "billing"},
    "student": {"discount", "verification", "cooldown"},
    "teacher": {"educator", "discount", "verification"},
    "broken": {"defect", "damaged", "warranty"},
    "defective": {"defect", "damaged", "warranty"},
}


def _tokens(text: str) -> list[str]:
    return [token for token in WORD_RE.findall(text.lower()) if token not in STOP_WORDS]


def _query_tokens(text: str) -> set[str]:
    tokens = set(_tokens(text))
    expanded = set(tokens)
    for token in tokens:
        expanded.update(QUERY_EXPANSIONS.get(token, ()))
    return expanded


@dataclass(frozen=True)
class KnowledgeChunk:
    source: str
    heading: str
    text: str
    authority: str
    tokens: frozenset[str]
    heading_tokens: frozenset[str]


class KnowledgeBase:
    """Small local retriever for the Markdown support knowledge base."""

    def __init__(self, directory: Path, max_chunk_chars: int = 1400):
        self.directory = Path(directory)
        self.max_chunk_chars = max_chunk_chars
        self.chunks = self._load()
        self.sources = frozenset(chunk.source for chunk in self.chunks)

    def _load(self) -> list[KnowledgeChunk]:
        if not self.directory.is_dir():
            raise FileNotFoundError(f"Knowledge directory not found: {self.directory}")

        chunks: list[KnowledgeChunk] = []
        for path in sorted(self.directory.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            sections = self._sections(text)
            authority = (
                "illustrative_case_study"
                if path.name == "case_studies.md"
                else "authoritative_policy_or_playbook"
            )
            for heading, section_text in sections:
                for part in self._split_long_section(section_text):
                    chunks.append(
                        KnowledgeChunk(
                            source=path.name,
                            heading=heading,
                            text=part,
                            authority=authority,
                            tokens=frozenset(_tokens(part)),
                            heading_tokens=frozenset(_tokens(heading)),
                        )
                    )
        if not chunks:
            raise ValueError(f"No Markdown knowledge found in {self.directory}")
        return chunks

    @staticmethod
    def _sections(text: str) -> list[tuple[str, str]]:
        sections: list[tuple[str, str]] = []
        heading = "Overview"
        body: list[str] = []
        for line in text.splitlines():
            match = HEADING_RE.match(line)
            if match:
                if body and "\n".join(body).strip():
                    sections.append((heading, "\n".join(body).strip()))
                heading = match.group(2)
                body = []
            else:
                body.append(line)
        if body and "\n".join(body).strip():
            sections.append((heading, "\n".join(body).strip()))
        return sections

    def _split_long_section(self, text: str) -> list[str]:
        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        output: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if current and len(current) + len(paragraph) + 2 > self.max_chunk_chars:
                output.append(current)
                current = paragraph
            else:
                current = f"{current}\n\n{paragraph}" if current else paragraph
        if current:
            output.append(current)
        return output

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        query_tokens = _query_tokens(query)
        if not query_tokens:
            return []

        phrase = query.lower().strip()
        ranked: list[tuple[float, KnowledgeChunk]] = []
        for chunk in self.chunks:
            heading_overlap = len(query_tokens & chunk.heading_tokens)
            body_overlap = len(query_tokens & chunk.tokens)
            if not heading_overlap and not body_overlap:
                continue

            score = heading_overlap * 4.0 + body_overlap * 1.25
            if phrase and phrase in chunk.text.lower():
                score += 4.0
            if chunk.authority == "illustrative_case_study":
                score *= 0.72
            ranked.append((score, chunk))

        ranked.sort(key=lambda item: (-item[0], item[1].source, item[1].heading))
        return [
            {
                "source": chunk.source,
                "heading": chunk.heading,
                "authority": chunk.authority,
                "text": chunk.text,
                "score": round(score, 3),
            }
            for score, chunk in ranked[: max(1, min(top_k, 8))]
        ]
