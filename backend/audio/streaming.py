"""
Audio streaming and sentence segmentation utilities.
Segments incoming text into natural spoken sentence chunks for low-latency TTS delivery.
"""
import re
from typing import Generator, List


# Regex pattern that splits sentences on punctuation followed by whitespace
SENTENCE_SPLIT_REGEX = re.compile(r'(?<=[.!?;\n])\s+')


class SentenceSegmenter:
    """
    Buffers streaming text tokens and yields complete sentences as soon as they are terminated.
    """
    def __init__(self):
        self._buffer: str = ""

    def feed(self, text: str) -> List[str]:
        self._buffer += text
        sentences: List[str] = []

        # Check if buffer has complete sentence ending with punctuation + whitespace
        parts = SENTENCE_SPLIT_REGEX.split(self._buffer)
        if len(parts) > 1:
            for sentence in parts[:-1]:
                clean = sentence.strip()
                if clean:
                    sentences.append(clean)
            self._buffer = parts[-1]

        return sentences

    def flush(self) -> List[str]:
        clean = self._buffer.strip()
        self._buffer = ""
        return [clean] if clean else []


def split_into_sentences(text: str) -> List[str]:
    """
    Splits an entire response text into spoken sentences.
    """
    if not text or not text.strip():
        return []

    # Clean multi-spaces
    cleaned = re.sub(r"\s+", " ", text).strip()
    # Protect common abbreviations before splitting
    protected = re.sub(r"\b(Mr|Mrs|Ms|Dr|Prof|vs|etc|e\.g|i\.e)\.", r"\1<DOT>", cleaned)

    splits = re.split(r'(?<=[.!?;\n])\s+', protected)
    sentences = []
    for s in splits:
        restored = s.replace("<DOT>", ".").strip()
        if restored:
            sentences.append(restored)

    return sentences
