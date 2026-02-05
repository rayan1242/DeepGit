# tools/merge_analysis.py
import logging

logger = logging.getLogger(__name__)

def merge_analysis(state, config):
    merged = {}
    
    # Identify if we are in Strict Personal Project mode
    is_personal = getattr(state, "project_type", "") == "Personal Project"
    
    # If Personal Project, our 'filtered_candidates' state contains the strictly filtered list 
    # from personal_analysis_node. We must use this as the base "Allow List".
    allowed_full_names = None
    if is_personal:
        allowed_full_names = {r["full_name"] for r in state.filtered_candidates}
        # Initialize merged dict with these vetted candidates
        for repo in state.filtered_candidates:
            merged[repo["full_name"]] = repo.copy()
            
    # Helper to merge in candidates from other streams
    def merge_stream(stream_candidates):
        for repo in stream_candidates:
            # If Strict Mode: Only merge if in allowed list
            if is_personal:
                if repo["full_name"] in merged:
                    merged[repo["full_name"]].update(repo)
                # Else: Skip (it was rejected by personal analysis)
            else:
                # Normal Mode: Union everything
                if repo["full_name"] in merged:
                    merged[repo["full_name"]].update(repo)
                else:
                    merged[repo["full_name"]] = repo.copy()

    # Merge activity and quality streams
    merge_stream(state.activity_candidates)
    merge_stream(state.quality_candidates)
    
    merged_list = list(merged.values())
    
    # Final check: If Personal, ensure we didn't accidentally lose scores or keep rejected ones
    if is_personal:
        # Re-filter just in case
         merged_list = [r for r in merged_list if r["full_name"] in allowed_full_names]

    state.filtered_candidates = merged_list
    logger.info(f"Merged analysis results: {len(merged_list)} candidates.")
    return {"filtered_candidates": merged_list}
