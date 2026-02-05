import logging
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from pathlib import Path
from pathlib import Path
import re
import json

# Load environment variables
dotenv_path = Path(__file__).resolve().parent.parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)

logger = logging.getLogger(__name__)

def evaluate_personal_project(repo_data: dict, readme_content: str, file_list: list) -> dict:
    """
    Evaluates a repository against the 13-point Personal Project Rubric.
    Returns a score (0-13) and a breakdown of matches.
    """
    score = 0
    signals = {}
    
    # ---------------------------
    # Fatal Checks (Immediate Fail)
    # ---------------------------
    
    # Check 0: Open Issues < 10 (User constraint: Personal projects usually don't have many issues)
    open_issues = repo_data.get('open_issues_count', 0)
    if open_issues >= 10:
        logger.info(f"Rejecting {repo_data.get('title')} due to high issues ({open_issues})")
        return {"score": 0, "is_personal_gold": False, "rejected": True, "reason": f"Too many issues ({open_issues})"}

    # Check 0.1: PR Count < 10
    pr_count = repo_data.get('pr_count', 0)
    if pr_count >= 10:
        logger.info(f"Rejecting {repo_data.get('title')} due to high PRs ({pr_count})")
        return {"score": 0, "is_personal_gold": False, "rejected": True, "reason": f"Too many PRs ({pr_count})"}
        
    # Check 0.2: Branch Count <= 5
    branch_count = repo_data.get('branch_count', 0)
    # Note: 0 might mean we failed to fetch, so we only fail on > 5
    if branch_count > 5:
        logger.info(f"Rejecting {repo_data.get('title')} due to high branch count ({branch_count})")
        return {"score": 0, "is_personal_gold": False, "rejected": True, "reason": f"Too many branches ({branch_count})"}

    # Check 0.5: Template/Boilerplate Detection in Title/Description
    # (README check is done in Soft Signals or here if content available)
    keywords = ["template", "boilerplate", "starter kit", "starter-kit", "scaffold"]
    title_desc = (repo_data.get('title', '') + " " + repo_data.get('description', '')).lower()
    if any(k in title_desc for k in keywords):
        logger.info(f"Rejecting {repo_data.get('title')} as template/boilerplate")
        return {"score": 0, "is_personal_gold": False, "rejected": True, "reason": "Detected as Template/Boilerplate"}

    # ---------------------------
    # Hard Signals (Metadata/API)
    # ---------------------------
    
    # 1. Contributors (Strongest Signal)
    # Note: We rely on passed data. If not available, we assume 1 (optimistic) or skip.
    contributors_count = repo_data.get('contributors_count', 1) 
    if 1 <= contributors_count <= 3:
        score += 1
        signals['contributors'] = True
    else:
        signals['contributors'] = False

    # 3. Repo Size (1MB - 200MB)
    size_kb = repo_data.get('size', 0) # API returns size in KB
    if 1000 <= size_kb <= 200000:
        score += 1
        signals['size'] = True
    else:
        signals['size'] = False

    # 8. Process Files (Absence matters)
    # Penalize if multiple exist: CODEOWNERS, SECURITY.md, CONTRIBUTING.md, Issue Templates
    corporate_files = ['CODEOWNERS', 'SECURITY.md', 'CONTRIBUTING.md', '.github/ISSUE_TEMPLATE']
    found_corporate = [f for f in corporate_files if any(f in path for path in file_list)]
    if len(found_corporate) <= 1:
        score += 1
        signals['process_files'] = True
    else:
        signals['process_files'] = False

    # 9. CI/CD Depth (0 or 1 workflow)
    workflows = [f for f in file_list if '.github/workflows' in f]
    if len(workflows) <= 1:
        score += 1
        signals['ci_cd'] = True
    else:
        signals['ci_cd'] = False
        
    # 11. Dependency Weight (Lean: 10-30) - Approximation via requirements.txt or similar
    # This is hard to check accurately without parsing, strict check might be too harsh.
    # We will skip strict check for now or assume PASS if file count is reasonable.
    signals['dependencies'] = "Skipped (Content analysis required)"

    # 13. Stars & Forks (Counter-signal)
    stars = repo_data.get('stars', 0)
    if 0 <= stars <= 50:
        score += 1
        signals['stars'] = True
    else:
        signals['stars'] = False # Too popular

    # ---------------------------
    # Soft Signals (LLM Analysis)
    # ---------------------------
    # We batch these into one LLM call to save time/tokens.
    
    llm_score, llm_signals = _analyze_soft_signals_with_llm(repo_data.get('title', ''), readme_content)
    score += llm_score
    signals.update(llm_signals)
    
    return {
        "score": score,
        "is_personal_gold": score >= 8,
        "rejected": False,
        "signals": signals
    }

def _analyze_soft_signals_with_llm(title: str, readme: str) -> tuple[int, dict]:
    """
    Uses LLM to evaluate:
    2. Issue/PR Ownership (Inferred from README context/tone)
    4. Commit History Pattern (Inferred if mentions "fixed edge case", "oops")
    5. README Style (Human written vs Auto)
    6. Feature Scope (Focused vs Everything)
    7. Repo Structure (Simple vs Microservices - approximated by description/readme)
    10. Branching (Inferred)
    12. Code Tone (Honest limitations vs Corp speak)
    """
    try:
        llm = ChatGroq(
            model="llama-3.1-8b-instant",
            temperature=0.0, # Deterministic for scoring
            max_tokens=1024
        )
        
        prompt_text = """
        You are an expert Code Auditor. Evaluate this repository README for "Personal Project Authenticity" based on these criteria.
        
        FATAL CONSTRAINT: If the README explicitly states this is a "template", "boilerplate", "starter kit", or "tutorial code", YOU MUST MARK 'is_template' as TRUE.
        STRICT REQUIREMENT: verify 'real_project'. It must appear to be a functioning tool or application with a specific purpose, NOT just a setup guide or "Hello World" scaffold.
        
        Repo Title: {title}
        README Snippet:
        {readme_content}
        
        Answer with JSON boolean (true/false) for each criterion:
        
        1. "author_ownership": Does the tone imply a single/small group author (e.g., "I built this", "My attempt") rather than a corporate "We"?
        2. "real_commit_pattern": Does the readme mention specific, honest fixes (e.g., "Fixed retry logic", "Added edge case handling") or limitations?
        3. "human_readme": Is the README written by a human explaining the "Why"? (Reject if generic/auto-generated).
        4. "focused_scope": Does it solve ONE clear problem with 5-10 features? (Reject "Everything app" or "All-in-one").
        5. "simple_structure": Does it describe a simple architecture (e.g. Frontend+Backend)? (Reject complex microservices).
        6. "no_corp_branching": Does it lack rigid release/branching terminology?
        7. "honest_tone":  Does it include TODOs, FIXMEs, or honest admission of bugs? (Reject over-polished tone).
        8. "is_template":  Is this a template, boilerplate, or starter kit? (True = BAD).
        9. "real_project": Does this look like a real, functioning project based on a specific topic (vs just a boilerplate)? (True = GOOD).
        
        Return ONLY valid JSON:
        {{
            "author_ownership": true/false,
            "real_commit_pattern": true/false,
            "human_readme": true/false,
            "focused_scope": true/false,
            "simple_structure": true/false,
            "no_corp_branching": true/false,
            "honest_tone": true/false,
            "is_template": true/false,
            "real_project": true/false
        }}
        """
        
        prompt = ChatPromptTemplate.from_template(prompt_text)
        chain = prompt | llm
        
        # Truncate README
        snippet = readme[:6000] if readme else "No README."
        
        response = chain.invoke({"title": title, "readme_content": snippet})
        content = response.content.strip()
        
        # Simple parsing (using eval for speed/simplicity in this contained context, or better regex)
        # We'll use regex to look for true/false to be safe against chatty LLM.
        # Try to find JSON block
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
        else:
            return 0, {}

        llm_score = sum(1 for k, v in data.items() if v is True and k != "is_template")
        
        # Penalize template detection via LLM
        if data.get("is_template", False):
            return -100, data
        
        # Check real project signal
        if not data.get("real_project", True): # Default to True if missing to be safe, but LLM should set it
             logger.info(f"LLM flagged {title} as NOT a real project")
             # We can treat this as a rejection or just heavy penalty. Rejection requested.
             # "make sure ... not a boiler plate or template ... real project"
             # If it's not a real project, it's likely boilerplate/toy.
             return -100, data

        return llm_score, data

    except Exception as e:
        logger.error(f"LLM Scoring failed: {e}")
        return 0, {}
