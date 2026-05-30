"""Common image processor — compression, format conversion, dedup, OCR, VLM description."""

import base64
import io
from typing import Any

from common.config_loader import get_config
from common.models.document import ImageElement
from common.util.logger import get_logger
from common.util.utils import md5_bytes
from elements.base import BaseElementProcessor
from elements.registry import get_element_registry

logger = get_logger()
registry = get_element_registry()


@registry.register
class ImageProcessor(BaseElementProcessor[ImageElement]):
    """Process images from all formats: compress, deduplicate, describe, OCR.

    Processing pipeline:
    1. Decompress → raw pixels
    2. Resize (if exceeds max dimensions)
    3. Compress to target format/quality
    4. Dedup (MD5-based, global across documents)
    5. Generate VLM description (optional, GPU node)
    6. OCR text extraction (if applicable)
    """

    processor_name = "image"
    element_class = ImageElement
    priority = 10

    def __init__(self):
        cfg = get_config()["elements"]["image"]
        self._max_width = cfg.get("max_width", 2048)
        self._max_height = cfg.get("max_height", 2048)
        self._quality = cfg.get("quality", 85)
        self._dedup_threshold = cfg.get("dedup_threshold", 0.95)
        self._generate_description = cfg.get("generate_description", True)
        self._description_lang = cfg.get("description_lang", "zh")

        self._llm = None
        self._seen_hashes: set[str] = set()

    def process(self, element: BaseElement, context: dict[str, Any] | None = None) -> BaseElement:
        if not isinstance(element, ImageElement):
            return element

        # Step 1: Normalize image (resize + compress)
        if element.image_data:
            element = self._normalize_image(element)

        # Step 2: Deduplication check
        if element.image_hash:
            if element.image_hash in self._seen_hashes:
                element.is_processed = True
                element.description = "[Duplicate image]"
                return element
            self._seen_hashes.add(element.image_hash)

        # Step 3: Generate VLM description
        if self._generate_description and element.image_data and not element.description:
            element = self._describe_image(element, context)

        element.is_processed = True
        return element

    def quality_score(self, element: BaseElement) -> float:
        if not isinstance(element, ImageElement):
            return 0.0

        score = 1.0

        # Penalize very small images (likely icons/decorations)
        if element.width < 32 or element.height < 32:
            score -= 0.5

        # Penalize extremely low resolution
        if element.width * element.height < 10000:
            score -= 0.3

        # Bonus for described images
        if element.description:
            score += 0.1

        return max(0.0, min(1.0, score))

    def _normalize_image(self, img: ImageElement) -> ImageElement:
        """Resize and compress image to standard format."""
        try:
            from PIL import Image

            pil_img = Image.open(io.BytesIO(img.image_data))

            # Convert to RGB if necessary
            if pil_img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", pil_img.size, (255, 255, 255))
                if pil_img.mode == "P":
                    pil_img = pil_img.convert("RGBA")
                background.paste(pil_img, mask=pil_img.split()[-1] if pil_img.mode in ("RGBA", "LA") else None)
                pil_img = background
            elif pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")

            # Resize if exceeds max dimensions
            if pil_img.width > self._max_width or pil_img.height > self._max_height:
                pil_img.thumbnail((self._max_width, self._max_height), Image.LANCZOS)

            # Save as JPEG with quality setting
            output = io.BytesIO()
            pil_img.save(output, format="JPEG", quality=self._quality)
            img.image_data = output.getvalue()
            img.image_hash = md5_bytes(img.image_data)
            img.width, img.height = pil_img.size
            img.format = "jpeg"

        except Exception as e:
            logger.warning(f"Image normalization failed: {e}")

        return img

    def _describe_image(self, img: ImageElement, context: dict[str, Any] | None = None) -> ImageElement:
        """Generate image description using VLM."""
        if img.image_data is None:
            return img

        try:
            img_b64 = base64.b64encode(img.image_data).decode("ascii")

            from infrastructure.llm.llm_adapter import get_llm_adapter
            if self._llm is None:
                self._llm = get_llm_adapter()

            prompt = self._build_description_prompt(context)
            description = self._llm.describe_image(img_b64, prompt=prompt, lang=self._description_lang)
            img.description = description
            logger.info(f"Image described: {img.element_id} ({len(description)} chars)")

        except Exception as e:
            logger.warning(f"Image description failed for {img.element_id}: {e}")

        return img

    def _build_description_prompt(self, context: dict[str, Any] | None = None) -> str:
        """Build context-aware prompt for image description."""
        lang = self._description_lang

        if context and context.get("document_title"):
            title = context["document_title"]
            return (
                f"这张图片来自文档《{title}》。"
                f"请用{lang}详细描述图片内容，包括：\n"
                "1. 图片类型（照片/图表/示意图/截图等）\n"
                "2. 主要内容\n"
                "3. 如果包含文字，提取文字内容\n"
                "4. 如果包含数据可视化，描述图表结构和关键数据"
            )

        return (
            f"请用{lang}详细描述这张图片的内容，包括：\n"
            "1. 图片类型（照片/图表/示意图/截图等）\n"
            "2. 主要内容\n"
            "3. 如果包含文字，提取文字内容\n"
            "4. 如果包含数据可视化，描述图表结构和关键数据"
        )
