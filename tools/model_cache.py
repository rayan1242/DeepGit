"""
Global model cache to avoid reloading models on each function call.
Models are loaded once and reused throughout the application lifecycle.
"""

import logging
from typing import Optional, Dict
from .embedding_utils import SentenceTransformer, CrossEncoder

logger = logging.getLogger(__name__)

# Global model instances - stores multiple models by name
_sem_models: Dict[str, SentenceTransformer] = {}
_cross_encoder_models: Dict[str, CrossEncoder] = {}


def get_semantic_model(model_name: str = "all-mpnet-base-v2") -> SentenceTransformer:
    """
    Get or load the semantic model (SentenceTransformer).
    Loads once per model name and reuses subsequent calls.
    
    Args:
        model_name: HuggingFace model name to use (default: "all-mpnet-base-v2")
    
    Returns:
        SentenceTransformer instance
    """
    global _sem_models
    if model_name not in _sem_models:
        logger.info(f"Loading semantic model: {model_name}")
        _sem_models[model_name] = SentenceTransformer(model_name)
    return _sem_models[model_name]


def get_cross_encoder_model(model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> CrossEncoder:
    """
    Get or load the cross-encoder model.
    Loads once per model name and reuses subsequent calls.
    
    Args:
        model_name: HuggingFace model name to use (default: "cross-encoder/ms-marco-MiniLM-L-6-v2")
    
    Returns:
        CrossEncoder instance
    """
    global _cross_encoder_models
    if model_name not in _cross_encoder_models:
        logger.info(f"Loading cross-encoder model: {model_name}")
        _cross_encoder_models[model_name] = CrossEncoder(model_name)
    return _cross_encoder_models[model_name]


def clear_cache():
    """
    Clear all cached models. Useful for testing or memory cleanup.
    """
    global _sem_models, _cross_encoder_models
    _sem_models.clear()
    _cross_encoder_models.clear()
    logger.info("Model cache cleared")
