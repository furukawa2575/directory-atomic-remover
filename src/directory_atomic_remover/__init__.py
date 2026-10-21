"""directory-atomic-remover: atomic directory replacement with background deletion."""

from .core import AtomicRemover, AtomicRemoverError

__all__ = ["AtomicRemover", "AtomicRemoverError"]
