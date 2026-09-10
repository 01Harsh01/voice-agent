"""
Tests for voice formatting and sentence segmentation.
"""
from backend.audio.streaming import SentenceSegmenter, split_into_sentences
from backend.llm.qwen import clean_voice_text


def test_clean_voice_text():
    raw = "### Header\n**NVIDIA** announced *new* GPUs! Visit `https://nvidia.com` for details. 1. Fast 2. Powerful."
    cleaned = clean_voice_text(raw)
    assert "###" not in cleaned
    assert "**" not in cleaned
    assert "*" not in cleaned
    assert "`" not in cleaned
    assert "NVIDIA announced new GPUs!" in cleaned
    assert "https://nvidia.com" in cleaned


def test_split_into_sentences_preserves_abbreviations_and_decimals():
    text = "The temperature is 32.5 degrees Celsius in Delhi. Dr. Smith reported that the storm will arrive tomorrow. Is it safe?"
    sentences = split_into_sentences(text)
    assert len(sentences) == 3
    assert sentences[0] == "The temperature is 32.5 degrees Celsius in Delhi."
    assert sentences[1] == "Dr. Smith reported that the storm will arrive tomorrow."
    assert sentences[2] == "Is it safe?"


def test_sentence_segmenter_streaming():
    segmenter = SentenceSegmenter()
    s1 = segmenter.feed("According to latest ")
    assert len(s1) == 0

    s2 = segmenter.feed("reports, NVIDIA revealed their new chip. ")
    assert len(s2) == 1
    assert "NVIDIA revealed their new chip." in s2[0]

    s3 = segmenter.feed("It boasts higher efficiency.")
    s_flush = segmenter.flush()
    assert len(s_flush) == 1
    assert "higher efficiency" in s_flush[0]
