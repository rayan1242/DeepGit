import logging
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
dotenv_path = Path(__file__).resolve().parent.parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)

logger = logging.getLogger(__name__)

def recommend_features(repo_name: str, readme_content: str, user_query: str) -> str:
    """
    Analyzes the repo and user query (JD context) to recommend 3 high-value features 
    that the user could add to impress interviewers.
    """
    
    # Initialize LLM
    llm = ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0.7,
        max_tokens=1024,
        max_retries=3,
    )

    prompt_template = """
    You are a Senior Engineering Manager & Interviewer at a top-tier tech company.
    A candidate is proposing to use the following open-source repository as a base for their portfolio/interview project.
    
    The candidate's target role/domain is implied by their search query: "{user_query}"
    
    Repository: {repo_name}
    Current Capabilities (from README):
    {readme_snippet}
    
    Your Task:
    Recommend exactly 3 "Star Features" the candidate should implement *on top* of this repo to demonstrate seniority and alignment with the target domain.
    The features should solve a business problem relevant to "{user_query}".
    
    Format your response exactly as follows for each feature:
    
    ### 1. [Feature Name]
    **Why**: [One sentence on business impact/relevance to the JD]
    **How**: [Technical implementation details: e.g. "Add a Redis cache layer...", "Integrate Kafka consumer...", "Add SHAP explainability..."]
    
    ### 2. [Feature Name]
    ...
    
    ### 3. [Feature Name]
    ...
    
    Do NOT include any intro or outro text. Just the 3 features.
    """
    
    # Truncate README
    readme_snippet = readme_content[:5000] if readme_content else "No detailed README available."

    prompt = ChatPromptTemplate.from_template(prompt_template)
    chain = prompt | llm
    
    try:
        response = chain.invoke({
            "repo_name": repo_name,
            "user_query": user_query,
            "readme_snippet": readme_snippet
        })
        return response.content.strip()
    except Exception as e:
        logger.error(f"Error generating feature recommendations: {e}")
        return "Could not generate recommendations due to an error."
