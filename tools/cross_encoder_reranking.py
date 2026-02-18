# tools/cross_encoder_reranking.py
import numpy as np
import logging
from sentence_transformers import CrossEncoder
from tools.model_cache import get_cross_encoder_model

logger = logging.getLogger(__name__)

def cross_encoder_reranking(state, config):
    from agent import AgentConfiguration
    agent_config = AgentConfiguration.from_runnable_config(config)
    cross_encoder = get_cross_encoder_model(agent_config.cross_encoder_model_name)
    # Use top candidates from semantic ranking (e.g., top 100)
    candidates_for_rerank = state.semantic_ranked[:100]
    logger.info(f"Re-ranking {len(candidates_for_rerank)} candidates with cross-encoder...")

    # Configuration for chunking
    CHUNK_SIZE = 2000        # characters per chunk
    MAX_DOC_LENGTH = 5000      # cap for long docs
    MIN_DOC_LENGTH = 200       # threshold for short docs

    def split_text(text, chunk_size=CHUNK_SIZE):
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
    
    def cross_encoder_rerank_func(query, candidates, top_n):
        for candidate in candidates:
            doc = candidate.get("combined_doc", "")
            # Limit document length if needed.
            if len(doc) > MAX_DOC_LENGTH:
                doc = doc[:MAX_DOC_LENGTH]
            try:
                if len(doc) < MIN_DOC_LENGTH:
                    # For very short docs, score directly.
                    score = cross_encoder.predict([[query, doc]], show_progress_bar=False)
                    candidate["cross_encoder_score"] = float(score[0])
                else:
                    # For longer docs, split into chunks.
                    chunks = split_text(doc)
                    pairs = [[query, chunk] for chunk in chunks]
                    scores = cross_encoder.predict(pairs, show_progress_bar=False)
                    # Combine scores: weighted average of max and mean scores.
                    max_score = np.max(scores) if scores is not None else 0.0
                    avg_score = np.mean(scores) if scores is not None else 0.0
                    candidate["cross_encoder_score"] = float(0.5 * max_score + 0.5 * avg_score)
            except Exception as e:
                logger.error(f"Error scoring candidate {candidate.get('full_name', 'unknown')}: {e}")
                candidate["cross_encoder_score"] = 0.0
        
        # Adjust scores based on documentation size (Boost & Penalty)
        import math
        LOW_DOC_THRESHOLD = 400 # approx 5-6 lines of text plus headers
        
        for candidate in candidates:
            r_size = candidate.get("readme_size", 0)
            a_size = candidate.get("arch_size", 0)
            
            # 1. Logarithmic boosting for content presence
            # 1KB -> ~1.5 boost magnitude per field with factor 0.5
            boost = 0.5 * (math.log10(r_size + 1) + math.log10(a_size + 1))
            
            # 2. Penalty for sparse documentation
            # Condition: Small README AND (No Arch OR Small Arch)
            penalty = 0.0
            if r_size < LOW_DOC_THRESHOLD:
                if a_size < LOW_DOC_THRESHOLD:
                    # Penalize heavily if both are missing/scant (approx 2-3 lines or less)
                    penalty = 5.0
            
            original_score = candidate["cross_encoder_score"]
            candidate["cross_encoder_score"] = original_score + boost - penalty
            
            # Log significant adjustments
            if abs(boost - penalty) > 0.1:
                 logger.info(f"Docs Score Adj for {candidate.get('full_name')}: {original_score:.3f} -> {candidate['cross_encoder_score']:.3f} (Boost:{boost:.2f}, Penalty:{penalty:.2f}, R:{r_size}, A:{a_size})")
        
        # Postprocessing: Shift all scores upward if any are negative.
        if not candidates:
            logger.warning("No candidates to rerank. Returning empty list.")
            return []
        all_scores = [candidate["cross_encoder_score"] for candidate in candidates]
        min_score = min(all_scores)
        if min_score < 0:
            shift = -min_score
            for candidate in candidates:
                candidate["cross_encoder_score"] += shift

        # Return top N candidates sorted by cross_encoder_score (descending)
        return sorted(candidates, key=lambda x: x["cross_encoder_score"], reverse=True)[:top_n]

    state.reranked_candidates = cross_encoder_rerank_func(
        state.user_query,
        candidates_for_rerank,
        int(agent_config.cross_encoder_top_n)
    )
    logger.info(f"Cross-encoder re-ranking complete: {len(state.reranked_candidates)} candidates remain.")
    return {"reranked_candidates": state.reranked_candidates}
