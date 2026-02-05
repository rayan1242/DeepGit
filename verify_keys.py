import os
import requests
from dotenv import load_dotenv
from langchain_groq import ChatGroq
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def check_github_key():
    token = os.getenv("GITHUB_API_KEY")
    if not token:
        logger.error("GITHUB_API_KEY not found in environment variables.")
        return False
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        response = requests.get("https://api.github.com/user", headers=headers)
        if response.status_code == 200:
            logger.info(f"GITHUB_API_KEY is valid. User: {response.json().get('login')}")
            return True
        else:
            logger.error(f"GITHUB_API_KEY is invalid or expired. Status: {response.status_code}, Response: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error checking GITHUB_API_KEY: {e}")
        return False

def check_groq_key():
    token = os.getenv("GROQ_API_KEY")
    if not token:
        logger.error("GROQ_API_KEY not found in environment variables.")
        return False
    
    try:
        llm = ChatGroq(
            api_key=token,
            model="llama-3.1-8b-instant",
            temperature=0.3,
            max_tokens=10
        )
        response = llm.invoke("Hello")
        logger.info("GROQ_API_KEY is working.")
        return True
    except Exception as e:
        logger.error(f"GROQ_API_KEY failed. Error: {e}")
        return False

if __name__ == "__main__":
    print("Checking keys...")
    github_ok = check_github_key()
    groq_ok = check_groq_key()
    
    if github_ok and groq_ok:
        print("\nAll keys are valid.")
    else:
        print("\nSome keys are invalid or missing.")
