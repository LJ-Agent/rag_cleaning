"""Element processor registry — central registration, discovery, and lookup."""

import importlib
import inspect
import pkgutil
from typing import Type

from common.models.document import BaseElement
from common.util.logger import get_logger
from elements.base import BaseElementProcessor

logger = get_logger()


class ElementProcessorRegistry:
    """Central registry for all element processors.

    Supports decorator registration + auto-discovery from package.
    """

    def __init__(self):
        self._processors: dict[str, BaseElementProcessor] = {}  # name → instance
        self._processor_classes: dict[str, type] = {}           # name → class
        # element-class-name → [processor_name, ...]
        self._element_map: dict[str, list[str]] = {}

    # ─── Registration ────────────────────────────────────────

    def register(self, processor_class: Type[BaseElementProcessor]):
        """Decorator: register a processor class."""
        instance = processor_class()
        name = instance.processor_name
        self._processors[name] = instance
        self._processor_classes[name] = processor_class

        if instance.element_class:
            elem_key = instance.element_class.__name__
            if elem_key not in self._element_map:
                self._element_map[elem_key] = []
            self._element_map[elem_key].append(name)
            self._element_map[elem_key].sort(
                key=lambda n: self._processors[n].priority
            )

        logger.info(f"Registered processor: {name} → {elem_key if instance.element_class else 'N/A'}")
        return processor_class

    def register_instance(self, processor: BaseElementProcessor):
        """Register an already-instantiated processor."""
        name = processor.processor_name
        self._processors[name] = processor
        self._processor_classes[name] = type(processor)
        if processor.element_class:
            elem_key = processor.element_class.__name__
            if elem_key not in self._element_map:
                self._element_map[elem_key] = []
            self._element_map[elem_key].append(name)
            self._element_map[elem_key].sort(key=lambda n: self._processors[n].priority)

    # ─── Auto-discovery ──────────────────────────────────────

    def discover(self, package_path: str = "elements.processors"):
        """Auto-discover processors by scanning a package for BaseElementProcessor subclasses."""
        try:
            package = importlib.import_module(package_path)
        except ImportError:
            logger.warning(f"Processor package not found: {package_path}")
            return

        if not hasattr(package, '__path__'):
            return

        for _, module_name, _ in pkgutil.iter_modules(package.__path__):
            if module_name.startswith("_"):
                continue
            full_name = f"{package_path}.{module_name}"
            try:
                module = importlib.import_module(full_name)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        inspect.isclass(attr)
                        and issubclass(attr, BaseElementProcessor)
                        and attr is not BaseElementProcessor
                        and not attr.__name__.startswith("_")
                    ):
                        inst = attr()
                        if inst.processor_name not in self._processors:
                            self.register(attr)
            except Exception as e:
                logger.warning(f"Failed to load processor module {full_name}: {e}")

    # ─── Lookup ──────────────────────────────────────────────

    def get_for_element(self, element: BaseElement) -> list[BaseElementProcessor]:
        """Get all enabled processors capable of handling an element, sorted by priority."""
        results = []
        for proc in self._processors.values():
            if proc.enabled and proc.can_process(element):
                results.append(proc)
        results.sort(key=lambda p: p.priority)
        return results

    def get_processor(self, name: str) -> BaseElementProcessor | None:
        """Get a specific processor by name."""
        return self._processors.get(name)

    def get_all(self) -> dict[str, BaseElementProcessor]:
        return dict(self._processors)

    def get_enabled(self) -> list[BaseElementProcessor]:
        return sorted(
            [p for p in self._processors.values() if p.enabled],
            key=lambda p: p.priority,
        )

    # ─── Configuration ───────────────────────────────────────

    def load_config(self, config: dict):
        """Apply configuration to processors (enable/disable, set params)."""
        elem_cfg = config.get("elements", {})
        for name, proc in self._processors.items():
            pc = elem_cfg.get(name, {})
            if "enabled" in pc:
                proc.enabled = pc["enabled"]
            if "priority" in pc:
                proc.priority = pc["priority"]

    # ─── Stats ────────────────────────────────────────────────

    def summary(self) -> dict:
        return {
            "total": len(self._processors),
            "enabled": sum(1 for p in self._processors.values() if p.enabled),
            "processors": {
                name: {
                    "enabled": p.enabled, "priority": p.priority,
                    "element_class": p.element_class.__name__ if p.element_class else "N/A",
                }
                for name, p in self._processors.items()
            },
        }


# ─── Global singleton ────────────────────────────────────────

_global_registry: ElementProcessorRegistry | None = None


def get_element_registry() -> ElementProcessorRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = ElementProcessorRegistry()
        _global_registry.discover("elements.processors")
        try:
            from common.config_loader import get_config
            _global_registry.load_config(get_config())
        except Exception:
            pass
    return _global_registry
