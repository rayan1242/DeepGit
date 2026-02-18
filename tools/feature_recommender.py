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
    
    # Initialize LLM (Groq or Bedrock)
    llm_provider = os.getenv("LLM_PROVIDER", "groq").lower()

    if llm_provider == "bedrock":
        from langchain_aws import ChatBedrock
        llm = ChatBedrock(
            model_id="anthropic.claude-3-sonnet-20240229-v1:0",
            model_kwargs={"temperature": 0.7, "max_tokens": 1024},
        )
    else:
        llm = ChatGroq(
            model="llama-3.1-8b-instant",
            temperature=0.7,
            max_tokens=1024,
            max_retries=3,
        )

    prompt_template = """
    You are a Senior Engineering Manager & Interviewer at a top-tier tech company.
    A candidate is applying for the following role/company (described in the Job Description below):
    
    === JOB DESCRIPTION (CONTEXT) ===
    {user_query}
    ===============================
    
    The candidate wants to use this Repository as a base for their portfolio project to impress the interviewers:
    
    === REPOSITORY: {repo_name} ===
    Current Capabilities (from README):
    {readme_snippet}
    ===============================
    
    Your Task:
    Recommend exactly 3 "Killer Features" the candidate should implement *on top* of this repo to bridge the gap between the repo's current state and the Job Description's requirements.
    Focus on adding sophisticated tech stack elements mentioned in the JD (e.g., if JD mentions Kafka/AWS/Docker and repo lacks them, suggest adding them).
    
    Format your response exactly as follows for each feature:
    
    ### 1. [Feature Name]
    **Why**: [Explains how this demonstrates a specific skill required by the company]
    **How**: [Technical implementation details: e.g. "Wrap the script in a Docker container...", "Replace the in-memory processed with a Redis queue..."]
    
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
