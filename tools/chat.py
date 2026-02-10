import logging
import re
from pathlib import Path
from typing import List
import itertools
import random
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

# --- Setup logging ---
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# --- Load .env ---
dotenv_path = Path(__file__).resolve().parent.parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)

# --- Initialize LLM ---
llm = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0.0,
    max_tokens=600,
)

# --- 1. Extract Company & Role ---
extract_prompt = ChatPromptTemplate.from_messages([
    ("system", "Extract Company Name and Job Role from the JD. Output JSON only: {{\"company\": \"...\", \"role\": \"...\"}}"),
    ("human", "{jd_text}")
])
extract_chain = extract_prompt | llm

def extract_company_role(jd_text: str):
    try:
        resp = extract_chain.invoke({"jd_text": jd_text}).content
        match = re.search(r"\{.*\}", resp, re.DOTALL)
        if match:
            import json
            data = json.loads(match.group())
            return data.get("company", "Unknown"), data.get("role", "Engineer")
    except Exception as e:
        logger.warning(f"Extraction error: {e}")
    return "Unknown", "Engineer"

# --- 2. Tech Stack Research ---
from duckduckgo_search import DDGS

def get_company_tech_stack(company: str) -> str:
    """Fetch tech stack info using DuckDuckGo."""
    if not company or company == "Unknown":
        return ""
    try:
        logger.info(f"Searching tech stack for {company}...")
        with DDGS() as ddgs:
            # Search for engineering blog or tech stack
            query = f"{company} engineering blog tech stack aws machine learning software tools"
            results = list(ddgs.text(query, max_results=3))
            if results:
                summary = "\n".join([f"- {r['title']}: {r['body']}" for r in results])
                logger.info(f"Found tech stack info: {summary[:100]}...")
                return summary
    except Exception as e:
        logger.warning(f"DDG Search failed: {e}")
    return ""

# --- 3. Generate Tag Pool ---
tag_prompt = ChatPromptTemplate.from_messages([
    ("system", """
You are a GitHub tag generation engine.

Given a company, role, job description, and EXTERNAL TECH STACK INFO:
- Analyze what specific tools/frameworks the company actually uses (e.g. 'kafka', 'kubernetes', 'react', 'tensorflow') based on the tech stack info.
- Generate 30 HIGH-SIGNAL GitHub tags
- Mix business domain + architecture + infra + languages + SPECIFIC TOOLS
- PRIORITIZE standard, existing GitHub topics (e.g., 'machine-learning', 'fintech', 'insurance', 'e-commerce')
- CRITICAL: Business domain in 3-4 tags MUST be single words if possible (e.g. 'healthcare' NOT 'healthcare-domain')
- AVOID generic suffixes like '-domain', '-tool', '-platform', '-system' unless standard
- Use lowercase, hyphenated GitHub-style topics
- Do not include company name in tags
- NO explanations
- NO categorization
- ONE tag per line
"""),
    ("human", """
Company: {company}
Role: {role}

Job Description:
{jd_text}

External Tech Stack Info (Use this to infer tools):
{tech_stack}
""")
])
tag_chain = tag_prompt | llm

def generate_tag_pool(jd_text: str, company: str, role: str) -> List[str]:
    logger.info(f"Generating tags for {company} - {role}...")
    
    # Fetch external info
    tech_stack = get_company_tech_stack(company)
    
    resp = tag_chain.invoke({
        "company": company,
        "role": role,
        "jd_text": jd_text,
        "tech_stack": tech_stack
    }).content

    tags = []
    for line in resp.splitlines():
        line = line.strip().lower()
        if not line: continue
        
        # Remove leader bullets/numbers
        line = re.sub(r"^[-*•0-9.]+\s*", "", line)
        
        # Keep only valid chars (a-z, 0-9, space, hyphen)
        line = re.sub(r"[^a-z0-9\s\-]+", "", line)
        line = line.strip()
        
        # Convert spaces to hyphens
        line = re.sub(r"\s+", "-", line)
        
        # Strict Filtering:
        # - Min length 3, Max length 40 (avoids sentences)
        # - Max 3 hyphens (avoids "cloud-software-and-ai-technology...")
        if len(line) < 3 or len(line) > 40:
            continue
        if line.count("-") > 3:
            continue
            
        tags.append(line)

    unique_tags = list(dict.fromkeys(tags))  # dedupe
    logger.info(f"Extracted {len(unique_tags)} tags: {unique_tags}")
    return unique_tags

# --- 3. Generate 1-2 tag queries ---
def generate_queries_from_tags(tags: list, max_queries: int = 300):
    single_tags = sorted(list(set(tags)))
    double_combos = set()
    
    # 2. Double tags (High precision)
    for combo in itertools.combinations(tags, 2):
        double_combos.add(" ".join(combo))
        
    double_tags = list(double_combos)
    random.shuffle(double_tags)
    
    # Prioritize single tags at the top
    final_queries = single_tags + double_tags
    
    return final_queries[:max_queries]

# --- 4. Utility function ---
def convert_to_search_tags(jd_text: str):
    company, role = extract_company_role(jd_text)
    tags = generate_tag_pool(jd_text, company, role)
    queries = generate_queries_from_tags(tags, max_queries=100)
    return {
        "company": company,
        "role": role,
        "tags": tags,
        "queries": queries
    }

# --- 5. Example usage ---
if __name__ == "__main__":
    sample_jd = """
Job Title: Data Scientist
Company: CCC Intelligent Solutions
Location: Chicago, IL, USA

About Us:
CCC Intelligent Solutions is a leading cloud software and AI technology provider for the insurance economy, empowering insurers, repairers, automakers, and partners with intelligent analytics and predictive solutions.

Responsibilities:
- Design and implement machine learning and AI models for cost prediction, impact modeling, and consumer applications.
- Convert research models into scalable production software.
- Collaborate with software engineers and product teams to integrate models into products.
- Use frameworks such as TensorFlow and PyTorch for model training and deployment.
- Utilize cloud services (e.g., AWS) and containerization (Docker, Kubernetes).
- Validate and optimize model performance; communicate insights to stakeholders.

Requirements:
- Master’s degree in Computer Science, AI, or related field.
- Proficiency in Python, SQL, and ML frameworks.
- Experience with cloud platforms and machine learning algorithms.
- Strong analytical skills and familiarity with statistical modeling.
- Knowledge of auto insurance domain preferred.

Salary Range: Competitive, typically mid‑100k to 200k+ based on experience and level.
"""
    results = convert_to_search_tags(sample_jd)
    print("\n--- Company & Role ---")
    print(results["company"], "|", results["role"])
    print("\n--- Generated Tags ---")
    print(results["tags"])
    print("\n--- Search Queries (2-3 tags each) ---")
    for q in results["queries"]:
        print(q)
