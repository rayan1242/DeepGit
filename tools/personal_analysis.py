import logging
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
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
    
    # Check 0: Open Issues < 10
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
    if branch_count > 5:
        logger.info(f"Rejecting {repo_data.get('title')} due to high branch count ({branch_count})")
        return {"score": 0, "is_personal_gold": False, "rejected": True, "reason": f"Too many branches ({branch_count})"}

    # Check 0.5: Template/Boilerplate Detection in Title/Description
    keywords = ["template", "boilerplate", "starter kit", "starter-kit", "scaffold"]
    title_desc = (repo_data.get('title', '') + " " + repo_data.get('description', '')).lower()
    if any(k in title_desc for k in keywords):
        logger.info(f"Rejecting {repo_data.get('title')} as template/boilerplate")
        return {"score": 0, "is_personal_gold": False, "rejected": True, "reason": "Detected as Template/Boilerplate"}

    # ---------------------------
    # Hard Signals (Metadata/API)
    # ---------------------------
    
    # 1. Contributors
    contributors_count = repo_data.get('contributors_count', 1) 
    if 1 <= contributors_count <= 3:
        score += 1
        signals['contributors'] = True
    else:
        signals['contributors'] = False

    # 3. Repo Size (1MB - 200MB)
    size_kb = repo_data.get('size', 0)
    if 1000 <= size_kb <= 200000:
        score += 1
        signals['size'] = True
    else:
        signals['size'] = False

    # 8. Process Files
    corporate_files = ['CODEOWNERS', 'SECURITY.md', 'CONTRIBUTING.md', '.github/ISSUE_TEMPLATE']
    found_corporate = [f for f in corporate_files if any(f in path for path in file_list)]
    if len(found_corporate) <= 1:
        score += 1
        signals['process_files'] = True
    else:
        signals['process_files'] = False

    # 9. CI/CD Depth
    workflows = [f for f in file_list if '.github/workflows' in f]
    if len(workflows) <= 1:
        score += 1
        signals['ci_cd'] = True
    else:
        signals['ci_cd'] = False
        
    # 11. Dependency Weight
    signals['dependencies'] = None  # Skipped for now

    # 13. Stars (Popularity metadata — not used for scoring)
    stars = repo_data.get('stars', 0)
    signals['stars'] = stars
    signals['star_band'] = (
        'low' if stars <= 20 else
        'medium' if stars <= 200 else
        'high'
    )

    # ---------------------------
    # Soft Signals (LLM Analysis)
    # ---------------------------
    llm_score, llm_signals = _analyze_soft_signals_with_llm(repo_data.get('title', ''), readme_content)

    # Reject immediately if LLM flags template / non-real project
    if llm_score < 0:
        return {
            "score": 0,
            "is_personal_gold": False,
            "rejected": True,
            "reason": "LLM flagged repo as template or non-real project",
            "signals": llm_signals
        }

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
    - Issue/PR Ownership
    - Commit History Pattern
    - README Style
    - Feature Scope
    - Repo Structure
    - Branching
    - Code Tone
    """
    try:
        llm_provider = os.getenv("LLM_PROVIDER", "groq").lower()

        if llm_provider == "bedrock":
            from langchain_aws import ChatBedrock
            llm = ChatBedrock(
                model_id="anthropic.claude-3-sonnet-20240229-v1:0",
                model_kwargs={"temperature": 0.0, "max_tokens": 1024},
            )
        else:
            llm = ChatGroq(
                model="llama-3.1-8b-instant",
                temperature=0.0,  # Deterministic
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
        
        1. "author_ownership"
        2. "real_commit_pattern"
        3. "human_readme"
        4. "focused_scope"
        5. "simple_structure"
        6. "no_corp_branching"
        7. "honest_tone"
        8. "is_template"
        9. "real_project"
        
        Return ONLY valid JSON.
        """
        
        prompt = ChatPromptTemplate.from_template(prompt_text)
        chain = prompt | llm
        
        snippet = readme[:6000] if readme else "No README."
        response = chain.invoke({"title": title, "readme_content": snippet})
        content = response.content.strip()
        
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
        if not data.get("real_project", True):
            logger.info(f"LLM flagged {title} as NOT a real project")
            return -100, data

        return llm_score, data

    except Exception as e:
        logger.error(f"LLM Scoring failed: {e}")
        return 0, {}
