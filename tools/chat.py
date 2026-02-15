import os
import re
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from pathlib import Path
from duckduckgo_search import DDGS

# Load environment variables
dotenv_path = Path(__file__).resolve().parent.parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)

# Step 1: Instantiate the Groq model
llm = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0.3,
    max_tokens=128,
    max_retries=3,
)

# Step 1.5: Entity Extraction Model & Prompt
llm_entity = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0.1,
    max_tokens=64,
    max_retries=3,
)

entity_prompt = ChatPromptTemplate.from_messages([
    ("system", 
     """Extract the core company or business entity name from the user's query relevant to finding open source software or company information.
     If no specific company or entity is mentioned, return 'None'.
     Return ONLY the name, no other text.
     
     Examples:
     Input: "What does Vercel use for frontend?" -> Output: Vercel
     Input: "Open source tools for data science" -> Output: None
     Input: "How does Uber manage microservices?" -> Output: Uber
     """),
    ("human", "{query}")
])

entity_chain = entity_prompt | llm_entity

ddgs = DDGS()

def get_context(query: str) -> str:
    # 1. Extract Entity
    try:
        entity_resp = entity_chain.invoke({"query": query})
        entity_name = entity_resp.content.strip()
        
        if not entity_name or entity_name.lower() == "none":
            return ""
            
        # 2. Search for the entity + "company business domain" only
        # strict=True sometimes helps with cleaner results
        results = list(ddgs.text(f"{entity_name} company business domain", max_results=1))
        if results:
             return results[0]["body"]
    except Exception as e:
        print(f"Error in entity extraction/search: {e}")
    return ""

# Step 2: Build the prompt with instructions for direct tag generation (NO iterative thinking)
prompt = ChatPromptTemplate.from_messages([
    ("system", 
     """You are a GitHub search optimization expert.
    
    
Your job is to:
1. Read a user's query about tools, research, or tasks.
2. Detect if the query mentions a specific programming language (for example, JavaScript or JS). If so, record that language as the target language.
3. Output up to five GitHub-style search tags or library names that maximize repository discovery.
   Use as many tags as necessary based on the query's complexity, but never more than five.
4. Append an additional tag at the end in the format target-[language] (e.g., target-javascript).
   If no specific language is mentioned, do not append any target tag.

Additional step:
- Before generating tags, internally infer the company's business domain 
<context>
    {context}
</context>
(e.g., auto insurance, fintech, healthcare, etc.) from the context or query, and create a short, natural search sentence describing the domain, problem type, and tech stack. Use this sentence internally to guide high-quality tag generation. Do NOT output the sentence; only output the final tags.

Output Format:
tag1:tag2[:tag3[:tag4[:tag5[:target-language]]]]

Rules:
- Use lowercase and hyphenated keywords (e.g., image-augmentation, chain-of-thought).
- Use terms commonly found in GitHub repo names, topics, or descriptions.
- Avoid generic terms like "python", "ai", "tool", "project" OR generic domain terms like "insurance" when a specific sub-domain is known (use "auto-insurance" instead).
- Do NOT output full phrases or vague words like "no-code", "framework", or "approach".
- Prefer real tools, popular methods, or dataset names when mentioned.
- If Business Context is provided, prioritize tags relevant to that company's specific sub-domain (e.g., "auto-insurance" for CCC/State Farm, "ride-sharing" for uber).
- Choose high-signal keywords to ensure the search yields the most relevant GitHub repositories.

Excellent Examples:

Input: "No code tool to augment image and annotation"
Output: image-augmentation:albumentations

Input: "Open-source tool for labeling datasets with UI"
Output: label-studio:streamlit

Input: "Data Scientist at Auto Insurance Company doing cost prediction"
Output: auto-insurance:vehicle-damage-assessment:claims-processing:cost-prediction

Input: "Visual reasoning models trained on multi-modal datasets"
Output: multimodal-reasoning:vlm

Input: "I want repos related to instruction-based finetuning for LLaMA 2"
Output: instruction-tuning:llama2

Input: "Repos around chain of thought prompting mainly for finetuned models"
Output: chain-of-thought:finetuned-llm

Input: "I want to fine-tune Gemini 1.5 Flash model"
Output: gemini-finetuning:flash002

Input: "Need repos for document parsing with vision-language models"
Output: document-understanding:vlm

Input: "How to train custom object detection models using YOLO"
Output: object-detection:yolov5

Input: "Segment anything-like models for interactive segmentation"
Output: interactive-segmentation:segment-anything

Input: "Synthetic data generation for vision model training"
Output: synthetic-data:image-augmentation

Input: "OCR pipeline for scanned documents"
Output: ocr:document-processing

Input: "LLMs with self-reflection or reasoning chains"
Output: self-reflection:chain-of-thought

Input: "Chatbot development using open-source LLMs"
Output: chatbot:llm

Input: "Deep learning-based object detection with YOLO and transformer architecture"
Output: object-detection:yolov5:transformer

Input: "Semantic segmentation for medical images using UNet with attention mechanism"
Output: semantic-segmentation:unet:attention

Input: "Find repositories implementing data augmentation pipelines in JavaScript"
Output: data-augmentation:target-javascript

Output must be ONLY the search tags separated by colons. Do not include any extra text, bullet points, or explanations.
"""),
    ("human", "{query}")
])

# Step 3: Chain the prompt with the LLM
chain = prompt | llm

# Step 4: Define user-facing function
def convert_to_search_tags(query: str) -> str:
    print(f"\\n[convert_to_search_tags] Input Query: {query}")
    try:
        context = get_context(query)
        if context:
            print(f"[convert_to_search_tags] Context found: {context[:100]}...")
        else:
            print("[convert_to_search_tags] No context found.")
            
        response = chain.invoke({"query": query, "context": context})
        tags = response.content.strip()
        print(f"[convert_to_search_tags] Output Tags: {tags}")
        return tags
    except Exception as e:
        print(f"Error generating tags: {e}")
        return query # Fallback to original query if generation fails

# Example usage
if __name__ == "__main__":
    # Example queries for testing:
    example_queries = [
        """
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

        """       # Should return target-javascript
    ]
    
    for q in example_queries:
        print(f"\\nInput: {q}")
        print(f"Output: {convert_to_search_tags(q)}")
