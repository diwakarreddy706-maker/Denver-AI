"""Unit tests for sentence-boundary detection and streaming TTS chunking."""

import pytest
import asyncio
from denver.audio.sentence_splitter import SentenceBoundaryDetector, stream_sentences
from denver.providers.base import AIProvider
from denver.providers.models import ProviderRequest, ProviderResponse, ProviderHealth, ProviderStatus, ProviderType, ModelInfo


def test_sentence_boundary_simple():
    detector = SentenceBoundaryDetector()
    sentences = detector.feed("Hello world. This is Denver speaking! How are you today?")
    assert sentences == [
        "Hello world.",
        "This is Denver speaking!",
        "How are you today?",
    ]
    tail = detector.flush()
    assert tail == []


def test_sentence_boundary_abbreviations():
    detector = SentenceBoundaryDetector()
    # Test abbreviations like Mr., Dr., e.g., and floating point numbers
    tokens = ["Good ", "morning, ", "Dr. ", "Smith! ", "The value is ", "3.14 ", "meters. ", "Have ", "a nice day."]
    results = []
    for token in tokens:
        results.extend(detector.feed(token))
    results.extend(detector.flush())

    assert results == [
        "Good morning, Dr. Smith!",
        "The value is 3.14 meters.",
        "Have a nice day.",
    ]


def test_sentence_boundary_multiple_sentences_in_one_chunk():
    detector = SentenceBoundaryDetector()
    sentences = detector.feed("First sentence. Second sentence! Third sentence? Fourth sentence.")
    assert len(sentences) == 4
    assert sentences[0] == "First sentence."
    assert sentences[1] == "Second sentence!"
    assert sentences[2] == "Third sentence?"
    assert sentences[3] == "Fourth sentence."


def test_sentence_boundary_tail_without_punctuation():
    detector = SentenceBoundaryDetector()
    sentences = detector.feed("This is an unpunctuated tail")
    assert sentences == []
    tail = detector.flush()
    assert tail == ["This is an unpunctuated tail"]


def test_sentence_boundary_clause_splitting_for_long_sentences():
    detector = SentenceBoundaryDetector()
    # Long clause over 18 words with a comma
    long_text = "When we explore the deepest and most fascinating mysteries of the cosmic quantum vacuum across countless billions of light years, we often discover strange anomalies."
    sentences = detector.feed(long_text)
    sentences.extend(detector.flush())
    assert len(sentences) == 2
    assert sentences[0].endswith(",")
    assert sentences[1] == "we often discover strange anomalies."


@pytest.mark.asyncio
async def test_stream_sentences_async_generator():
    async def mock_token_stream():
        tokens = ["The ", "universe ", "is ", "vast. ", "It ", "contains ", "billions ", "of ", "galaxies."]
        for t in tokens:
            await asyncio.sleep(0.001)
            yield t

    output = []
    async for sentence in stream_sentences(mock_token_stream()):
        output.append(sentence)

    assert output == [
        "The universe is vast.",
        "It contains billions of galaxies.",
    ]


@pytest.mark.asyncio
async def test_stream_sentences_no_lost_text_order_preserved():
    # Test that no words are dropped or scrambled
    input_text = "Sentence one is here. Sentence two is very clear. And here is the final fragment"
    words = input_text.split(" ")

    async def word_stream():
        for w in words:
            yield w + " "

    reconstructed_sentences = []
    async for s in stream_sentences(word_stream()):
        reconstructed_sentences.append(s)

    combined = " ".join(reconstructed_sentences)
    for word in words:
        assert word in combined
    assert reconstructed_sentences[-1] == "And here is the final fragment"


class DummyNonStreamingProvider(AIProvider):
    @property
    def name(self) -> str:
        return "dummy_non_streaming"

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.LOCAL

    @property
    def enabled(self) -> bool:
        return True

    @property
    def default_model(self) -> str:
        return "dummy"

    async def check_health(self) -> ProviderHealth:
        return ProviderHealth(provider_name=self.name, status=ProviderStatus.HEALTHY, provider_type=self.provider_type, model_name=self.default_model)

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            text="This is a whole response from a provider without native streaming.",
            provider_name=self.name,
            model_name=self.default_model,
            success=True,
        )


@pytest.mark.asyncio
async def test_fallback_when_provider_lacks_streaming(caplog):
    import logging
    caplog.set_level(logging.INFO)
    provider = DummyNonStreamingProvider()
    req = ProviderRequest(messages=[{"role": "user", "content": "hi"}])
    
    tokens = []
    async for token in provider.stream_generate(req):
        tokens.append(token)

    assert len(tokens) == 1
    assert tokens[0] == "This is a whole response from a provider without native streaming."
    # Verify fallback notice logged explicitly
    assert any("does not implement native token streaming" in record.message for record in caplog.records)
