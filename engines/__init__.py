"""TTS engine registry.

Engines are imported lazily so that starting the app does not pay for
loading onnxruntime or torch until a voice from that engine is used.
"""

from voices import get_voice

from .base import Chunk, Engine

_instances: dict[str, Engine] = {}


def get_engine(name: str) -> Engine:
    if name not in _instances:
        if name == "kokoro":
            from .kokoro_engine import KokoroEngine
            _instances[name] = KokoroEngine()
        elif name == "piper":
            from .piper_engine import PiperEngine
            _instances[name] = PiperEngine()
        else:
            raise ValueError(f"Unknown engine '{name}'")
    return _instances[name]


def engine_for_voice(voice_id: str) -> Engine:
    return get_engine(get_voice(voice_id).engine)


__all__ = ["Chunk", "Engine", "get_engine", "engine_for_voice"]
