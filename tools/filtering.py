# tools/filtering.py
import logging

logger = logging.getLogger(__name__)

def threshold_filtering(state, config):
    """
    Filters repos based primarily on semantic relevance.
    
    Key philosophy:
    - Stars are NOT a hard filter (low stars ≠ bad project)
    - Cross-encoder score is the main quality gate
    - Hardware constraints (if any) are applied last
    """

    # Import config lazily to avoid circular deps
    from agent import AgentConfiguration
    agent_config = AgentConfiguration.from_runnable_config(config)

    filtered = []

    for repo in state.reranked_candidates:
        ce_score = repo.get("cross_encoder_score", 0.0)

        # ✅ ONLY filter on semantic quality
        if ce_score < agent_config.cross_encoder_threshold:
            continue

        # ⭐ stars are kept as metadata / ranking signal only
        filtered.append(repo)

    # Safety net: if everything was filtered out, keep all
    if not filtered:
        logger.warning(
            "All candidates filtered out by cross-encoder threshold; "
            "falling back to full reranked list."
        )
        filtered = list(state.reranked_candidates)

    # 2) Optional hardware filtering
    if getattr(state, "hardware_spec", None):
        hw_filtered = getattr(state, "hardware_filtered", None)
        if hw_filtered:
            filtered = hw_filtered
        else:
            logger.info(
                "Hardware spec provided but no hardware_filtered list found; "
                "skipping hardware filter."
            )

    state.filtered_candidates = filtered

    logger.info(
        f"Filtering complete: {len(filtered)} candidates remain "
        f"(semantic threshold{' + hardware filter' if state.hardware_spec else ''})."
    )

    return {"filtered_candidates": filtered}
