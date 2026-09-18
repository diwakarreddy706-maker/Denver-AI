# Denver Embedding Providers Architecture

## Overview
Denver employs a pluggable embedding architecture defined in `denver.memory.embeddings`.

---

## 1. Provider Abstraction

```python
class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        ...

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...
```

---

## 2. Implemented Providers

### 1. `DeterministicLexicalEmbedder` (Default / Fallback)
- **Dimension**: 128
- **Dependencies**: Pure Python standard library (`hashlib`, `math`, `re`, `collections`).
- **Compatibility**: 100% CPython 3.14.7 compatible on Windows. Zero C++ native extensions or compiler required.
- **Algorithm**:
  - Extracts word tokens and character trigrams.
  - Hashes tokens with SHA-256 into a 128-bucket vector with signed projection.
  - Applies L2-normalization for cosine distance metric.
- **Role**: Deterministic lexical/vector fallback ensuring the application and test suites never fail due to offline status or missing local models.

### 2. `OllamaEmbeddingProvider` (Local LLM Provider)
- **Dimension**: Configurable (e.g. 768 for `nomic-embed-text`, 384 for `all-minilm`).
- **API Support**: Supports standard `/api/embeddings` and OpenAI-compatible `/v1/embeddings` local Ollama endpoints.
- **Error Handling**: Gracefully falls back to `DeterministicLexicalEmbedder` upon connection timeout or unavailability.

---

## 3. Storage
Embeddings are serialized into packed binary float arrays (`struct.pack(f"{len(vec)}f", *vec)`) and stored in the `memory_embeddings` SQLite table.
