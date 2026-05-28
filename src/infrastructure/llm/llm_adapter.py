"""LLM adapter — unified interface for text + vision models."""
from typing import AsyncIterator

from openai import AsyncOpenAI, OpenAI

from common.config_loader import get_config
from common.exception.exceptions import ElementProcessingException
from common.util.logger import get_logger

logger = get_logger()


class LLMAdapter:
    """Unified LLM client for cleaning tasks: text classification, image description, formula recognition."""

    def __init__(self):
        cfg = get_config()["llm"]
        self._api_key = cfg["api_key"]
        self._base_url = cfg["base_url"]
        self._chat_model = cfg["chat_model"]
        self._vision_model = cfg.get("vision_model", cfg["chat_model"])
        self._embedding_model = cfg["embedding_model"]
        self._local_embedding_model = cfg.get("local_embedding_model")
        self._max_tokens = cfg["max_tokens"]
        self._temperature = cfg["temperature"]
        self._timeout = cfg.get("request_timeout", 120)
        self._max_retries = cfg.get("max_retries", 3)

        self._client: OpenAI | None = None
        self._async_client: AsyncOpenAI | None = None
        self._local_embedder = None

        use_local = cfg.get("use_local_embedding", False) or not cfg.get("api_key")
        if use_local:
            self._init_local_embedder()

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self._timeout,
                max_retries=self._max_retries,
            )
        return self._client

    def _get_async_client(self) -> AsyncOpenAI:
        if self._async_client is None:
            self._async_client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self._timeout,
                max_retries=self._max_retries,
            )
        return self._async_client

    # ─── Embedding ─────────────────────────────────────────

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Batch compute embeddings."""
        try:
            response = self._get_client().embeddings.create(
                model=self._embedding_model,
                input=texts,
            )
            return [d.embedding for d in response.data]
        except Exception as e:
            raise ElementProcessingException(f"Embedding failed: {e}", element_type="embedding")

    # ─── Chat Completion ───────────────────────────────────

    def chat(self, messages: list[dict], model: str | None = None) -> str:
        """Non-streaming chat completion, returns content string."""
        try:
            response = self._get_client().chat.completions.create(
                model=model or self._chat_model,
                messages=messages,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise ElementProcessingException(f"LLM chat failed: {e}")

    # ─── Vision / Image Description ────────────────────────

    def describe_image(self, image_base64: str, prompt: str | None = None, lang: str = "zh") -> str:
        """Generate image description using vision-capable model."""
        if prompt is None:
            prompt = f"请详细描述这张图片的内容，使用{lang}语言。如果图片中包含表格，请描述表格结构和数据；如果包含文字，请提取文字内容。"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                ],
            }
        ]
        return self.chat(messages, model=self._vision_model)

    def recognize_formula(self, image_base64: str) -> str:
        """Recognize formula from image, return LaTeX."""
        prompt = "请识别图片中的数学公式，输出标准的LaTeX格式。只输出LaTeX代码，不要任何额外文字。"
        return self.describe_image(image_base64, prompt=prompt, lang="zh")

    # ─── Classification ────────────────────────────────────

    def classify_content(self, text: str, labels: list[str]) -> str:
        """Classify text into one of the given labels."""
        messages = [
            {"role": "system", "content": "你是一个精准的文本分类器。只输出类别名称，不要任何解释。"},
            {"role": "user", "content": f"将以下文本分类为以下类别之一：{', '.join(labels)}。\n\n文本：{text}"},
        ]
        result = self.chat(messages, model=self._chat_model).strip()
        return result if result in labels else labels[0]

    # ─── Local Embedding ───────────────────────────────────

    def _init_local_embedder(self):
        if self._local_embedder is None and self._local_embedding_model:
            from sentence_transformers import SentenceTransformer
            self._local_embedder = SentenceTransformer(self._local_embedding_model)
            logger.info(f"Local embedding model loaded: {self._local_embedding_model}")

    def embed_local(self, texts: list[str]) -> list[list[float]]:
        """Use local sentence-transformers for embedding."""
        self._init_local_embedder()
        if self._local_embedder is None:
            raise ElementProcessingException("Local embedding model not configured", element_type="embedding")
        embeddings = self._local_embedder.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()


_llm_adapter: LLMAdapter | None = None


def get_llm_adapter() -> LLMAdapter:
    global _llm_adapter
    if _llm_adapter is None:
        _llm_adapter = LLMAdapter()
    return _llm_adapter
