import logging
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables (reuse logic from existing tools)
dotenv_path = Path(__file__).resolve().parent.parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)

logger = logging.getLogger(__name__)

def generate_resume_bullets(repo_name: str, description: str, readme_content: str = "") -> str:
    """
    Generates 4-5 impact-driven resume bullet points for a given repository.
    """
    
    # Initialize LLM (Groq or Bedrock)
    llm_provider = os.getenv("LLM_PROVIDER", "groq").lower()

    if llm_provider == "bedrock":
        from langchain_aws import ChatBedrock
        llm = ChatBedrock(
            model_id="anthropic.claude-3-sonnet-20240229-v1:0",
            model_kwargs={"temperature": 0.7, "max_tokens": 512},
        )
    else:
        llm = ChatGroq(
            model="llama-3.1-8b-instant",
            temperature=0.7,
            max_tokens=512,
            max_retries=3,
        )

    prompt_template = """
    You are an expert technical resume writer. 
    Your task is to write 4-5 strong, impact-driven bullet points for a project section in a resume, based on the following repository details.
    
    Repository: {repo_name}
    Description: {description}
    
    Context (README Snippet):
    {readme_snippet}
    
    Guidelines:
    - Use active verbs (Developed, Engineered, implemented, Optimized).
    - Use quantifiable metrics (e.g., "processed 1M+ records", "reduced latency by 50%").
    - Highlight technologies used (e.g., Python, RAG, LangChain, Transformers).
    - Focus on the *problem solved* and the *technical solution*.
    - If possible, infer metrics or scale (e.g., "processed large-scale datasets", "reduced latency").
    - Format as a simple list of bullet points.
    - Do NOT include introductory text like "Here are the bullets". Just the bullets.
    """
    
    # Truncate README to avoid context limit issues
    readme_snippet = readme_content[:4000] if readme_content else "No detailed README available."

    prompt = ChatPromptTemplate.from_template(prompt_template)
    chain = prompt | llm
    
    try:
        response = chain.invoke({
            "repo_name": repo_name,
            "description": description,
            "readme_snippet": readme_snippet
        })
        return response.content.strip()
    except Exception as e:
        logger.error(f"Error generating resume bullets: {e}")
        return "Could not generate resume bullets due to an error."
