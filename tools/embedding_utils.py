"""
Lightweight embedding utilities using transformers directly.
Replaces sentence-transformers to reduce Docker image size.
"""

import logging
import torch
import numpy as np
from transformers import AutoTokenizer, AutoModel
from typing import Union, List

logger = logging.getLogger(__name__)

# Cache for loaded models
_model_cache = {}

def get_device():
    """Get the appropriate device (CPU by default for lightweight containers)."""
    device = "cpu"
    if torch.cuda.is_available():
        device = "cuda"
    return device

class LightweightEmbedder:
    """Lightweight sentence embedder using transformers."""
    
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        """
        Initialize embedder with a model.
        
        Args:
            model_name: HuggingFace model identifier
        """
        self.model_name = model_name
        self.device = get_device()
        
        if model_name not in _model_cache:
            logger.info(f"Loading embedder model: {model_name}")
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModel.from_pretrained(model_name)
            self.model.to(self.device)
            self.model.eval()
            _model_cache[model_name] = (self.tokenizer, self.model)
        else:
            self.tokenizer, self.model = _model_cache[model_name]
    
    def encode(self, sentences: Union[str, List[str]], normalize_embeddings: bool = False) -> np.ndarray:
        """
        Encode sentences to embeddings.
        
        Args:
            sentences: Single sentence or list of sentences
            normalize_embeddings: Whether to normalize embeddings
            
        Returns:
            numpy array of embeddings
        """
        if isinstance(sentences, str):
            sentences = [sentences]
        
        with torch.no_grad():
            encoded_input = self.tokenizer(
                sentences, 
                padding=True, 
                truncation=True, 
                return_tensors="pt",
                max_length=512
            )
            encoded_input = {k: v.to(self.device) for k, v in encoded_input.items()}
            model_output = self.model(**encoded_input)
            
            # Mean pooling
            token_embeddings = model_output[0]
            input_mask_expanded = encoded_input['attention_mask'].unsqueeze(-1).expand(token_embeddings.size()).float()
            embeddings = torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)
        
        if normalize_embeddings:
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
        
        return embeddings.cpu().numpy()

class LightweightCrossEncoder:
    """Lightweight cross-encoder for relevance scoring using transformers."""
    
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """
        Initialize cross-encoder with a model.
        
        Args:
            model_name: HuggingFace model identifier
        """
        self.model_name = model_name
        self.device = get_device()
        
        if model_name not in _model_cache:
            logger.info(f"Loading cross-encoder model: {model_name}")
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModel.from_pretrained(model_name)
            self.model.to(self.device)
            self.model.eval()
            _model_cache[model_name] = (self.tokenizer, self.model)
        else:
            self.tokenizer, self.model = _model_cache[model_name]
    
    def predict(self, scores_input: Union[List[str], List[List[str]]]) -> np.ndarray:
        """
        Predict relevance scores.
        
        Args:
            scores_input: Single pair or list of pairs [query, text]
            
        Returns:
            numpy array of scores
        """
        if isinstance(scores_input[0], str):
            scores_input = [scores_input]
        
        with torch.no_grad():
            encoded = self.tokenizer(
                scores_input,
                padding=True,
                truncation=True,
                return_tensors="pt",
                max_length=512
            )
            encoded = {k: v.to(self.device) for k, v in encoded.items()}
            outputs = self.model(**encoded)
            logits = outputs.logits
        
        scores = logits.cpu().numpy()
        return scores


# Convenience factories that mimic sentence_transformers API
def SentenceTransformer(model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> LightweightEmbedder:
    """Factory function to create a SentenceTransformer-like object."""
    return LightweightEmbedder(model_name)

def CrossEncoder(model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> LightweightCrossEncoder:
    """Factory function to create a CrossEncoder-like object."""
    return LightweightCrossEncoder(model_name)
