"""
Speech-to-Text (STT) processing module.
Handles transcripts sent from the client or audio payload parsing.
"""
from typing import Optional


class STTHandler:
    def __init__(self):
        pass

    def process_transcript(self, raw_transcript: str) -> str:
        """
        Normalizes and sanitizes user speech transcript.
        """
        if not raw_transcript:
            return ""
        cleaned = " ".join(raw_transcript.strip().split())
        return cleaned
