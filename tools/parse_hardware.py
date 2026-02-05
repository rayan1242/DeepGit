# tools/parse_hardware_spec.py
import re, logging
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
dotenv_path = Path(__file__).resolve().parent.parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)

# Dedicated LLM for hardware parsing (avoiding dependency on chat.py's shared chain)
llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0.0) 

logger = logging.getLogger(__name__)

VALID_SPECS = ("cpu-only", "low-memory", "mobile")

HARDWARE_PATTERNS = {
    "cpu-only":   [r"cpu[- ]only", r"no[- ]?gpu",  r"gpu[- ]poor", r"lightweight"],
    "low-memory": [r"low[- ]?memory", r"small[- ]?memory"],
    "mobile":     [r"mobile", r"raspberry", r"android"],
}

PROMPT_TEMPLATE = (
    "Extract any hardware constraints from the user query. "
    "Return exactly one of: cpu-only, low-memory, mobile, NONE."
)

def parse_hardware_spec(state, config):
    q = state.user_query.lower()

    # 1) Fast heuristic
    for spec, patterns in HARDWARE_PATTERNS.items():
        if any(re.search(pat, q) for pat in patterns):
            logger.info(f"[Hardware] regex -> {spec}")
            state.hardware_spec = spec
            return {"hardware_spec": spec}

    # 2) LLM fallback
    # 2) LLM fallback
    # Use a simple direct prompt since we have our own LLM instance now
    prompt = ChatPromptTemplate.from_template("{text}")
    chain = prompt | llm
    
    full = f"{PROMPT_TEMPLATE}\n\nUser query:\n{state.user_query}"
    resp = chain.invoke({"text": full}).content.strip().lower()
    spec = resp if resp in VALID_SPECS else None
    logger.info(f"[Hardware] LLM  -> {spec}")
    state.hardware_spec = spec
    return {"hardware_spec": spec}
