"""Streaming Sentence Boundary Detector for Low-Latency Text-to-Speech (TTS).

Buffers incoming streamed LLM tokens and yields clean, complete sentence clauses
the moment punctuation or natural speech boundaries are reached.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any

# Recognized abbreviations where trailing period is NOT a sentence terminator
ABBREVIATIONS = {
    "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.",
    "vs.", "etc.", "e.g.", "i.e.", "st.", "a.m.", "p.m.",
    "co.", "inc.", "ltd.", "dept.", "approx.", "est.", "fig."
}

# Regex to detect sentence boundaries:
# Matches ., !, ? followed by whitespace or end-of-string, or double newlines
SENTENCE_SPLIT_PATTERN = re.compile(r"([.!?]+(?:\s+|$)|(?:\n\s*\n+))")


class SentenceBoundaryDetector:
    """Buffers streamed tokens and extracts complete sentences for streaming TTS synthesis."""

    def __init__(self, max_clause_words: int = 25) -> None:
        self.max_clause_words = max_clause_words
        self.buffer = ""

    def feed(self, token: str) -> list[str]:
        """Feed a new token chunk into the buffer and return any completed sentences."""
        if not token:
            return []

        self.buffer += token
        completed_sentences: list[str] = []

        while True:
            match = SENTENCE_SPLIT_PATTERN.search(self.buffer)
            if not match:
                # Check for clause split if buffer has grown too long without punctuation
                clause = self._check_long_clause_split()
                if clause:
                    completed_sentences.append(clause)
                    continue
                break

            split_pos = match.end()
            candidate = self.buffer[:split_pos].strip()

            # If the sentence is excessively long before the punctuation mark, split at a clause boundary
            words = candidate.split()
            if len(words) >= self.max_clause_words:
                for delim in [", ", "; ", " - ", " -- "]:
                    idx = candidate.find(delim, 30)
                    if idx != -1:
                        split_pos = idx + len(delim)
                        candidate = self.buffer[:split_pos].strip()
                        break

            # Check if this period belongs to a decimal number (e.g. "3.14" or "$19.99")
            match_start = match.start()
            if match_start > 0 and self.buffer[match_start] == ".":
                before_char = self.buffer[match_start - 1]
                after_char = self.buffer[match_start + 1] if match_start + 1 < len(self.buffer) else ""
                if before_char.isdigit() and after_char.isdigit():
                    # Move past this number without splitting
                    rest = self.buffer[split_pos:]
                    sub_match = SENTENCE_SPLIT_PATTERN.search(rest)
                    if not sub_match:
                        break
                    split_pos += sub_match.end()
                    candidate = self.buffer[:split_pos].strip()

            # Check if candidate ends with a known abbreviation (e.g. "Dr.", "e.g.")
            last_word = candidate.split()[-1].lower() if candidate.split() else ""
            if last_word in ABBREVIATIONS:
                # This is an abbreviation, do not split yet; search for next terminator
                rest = self.buffer[split_pos:]
                sub_match = SENTENCE_SPLIT_PATTERN.search(rest)
                if not sub_match:
                    break
                split_pos += sub_match.end()
                candidate = self.buffer[:split_pos].strip()

            # We have a valid sentence
            if candidate:
                completed_sentences.append(candidate)
            self.buffer = self.buffer[split_pos:].lstrip()

        return completed_sentences

    def _check_long_clause_split(self) -> str | None:
        """Split excessively long unpunctuated text at a comma, semicolon, or dash."""
        words = self.buffer.split()
        if len(words) >= self.max_clause_words:
            # Look for a comma, semicolon, or dash after word 10
            for delim in [", ", "; ", " - ", " -- "]:
                idx = self.buffer.find(delim, 30)
                if idx != -1:
                    split_pos = idx + len(delim)
                    clause = self.buffer[:split_pos].strip()
                    self.buffer = self.buffer[split_pos:].lstrip()
                    return clause
        return None

    def flush(self) -> list[str]:
        """Flush and return any remaining text in the buffer as the final sentence."""
        remaining = self.buffer.strip()
        self.buffer = ""
        if remaining:
            return [remaining]
        return []


async def stream_sentences(token_stream: AsyncIterator[str]) -> AsyncIterator[str]:
    """Asynchronous generator converting an incoming token stream into complete sentences."""
    detector = SentenceBoundaryDetector()

    async for token in token_stream:
        sentences = detector.feed(token)
        for sentence in sentences:
            if sentence:
                yield sentence

    # Flush final tail fragment
    for final_sentence in detector.flush():
        if final_sentence:
            yield final_sentence
