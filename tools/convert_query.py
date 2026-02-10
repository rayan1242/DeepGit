# tools/convert_query.py
import logging
from tools.chat import convert_to_search_tags
from tools.parse_hardware import parse_hardware_spec

logger = logging.getLogger(__name__)

def convert_searchable_query(state, config):
    # 1) Check if we should skip LLM expansion (e.g. user clicked a specific tag)
    if hasattr(state, "skip_llm_expansion") and state.skip_llm_expansion:
        # Just use the user query directly. 
        # CAUTION: Ensure it's formatted as expected by github.py (e.g. space-separated is fine as a single query term if no ':' present)
        state.searchable_query = state.user_query
        logger.info(f"Skipping LLM expansion. Using raw user query: {state.searchable_query}")
        return {"searchable_query": state.searchable_query}

    # 2) Extract hardware_spec so we can remove it from the tags
    parse_hardware_spec(state, config)
    hw = state.hardware_spec or ""

    # 3) Generate tags using the new high-recall engine
    # The new function returns a dict: {'tags': [...], 'queries': [...], 'company': ...}
    result = convert_to_search_tags(state.user_query)
    
    # We use the 'tags' list which contains high-signal topics
    raw_tags = result.get("tags", [])
    
    # Fallback: simple extraction if LLM fails or returns nothing
    if not raw_tags:
        logger.warning("LLM tag generation yielded 0 tags. Using fallback extraction.")
        import re
        # Basic extraction of interesting words > 3 chars
        words = re.findall(r"\b[a-zA-Z0-9-]{3,}\b", state.user_query.lower())
        stop_words = {"limit", "hardware", "constraint", "project", "personal", "github", "search", "find", "repos", "repositories"} 
        raw_tags = [w for w in words if w not in stop_words]

    # 3) Filter out any tag that matches the hardware spec token
    filtered = [tag for tag in raw_tags if tag and tag != hw]
    
    # Join into colon-separated string to maintain compatibility with existing state structure
    searchable = ":".join(filtered)

    # Final check: if still empty, use generic term to avoid crash
    if not searchable:
        searchable = "python" # absolute last resort
        logger.warning("Query still empty after fallback. Using 'python' default.")

    # 4) Store and log the cleaned searchable query
    state.searchable_query = searchable
    logger.info(f"Converted searchable query (hardware removed): {searchable}")
    return {"searchable_query": searchable}
