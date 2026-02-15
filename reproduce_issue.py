import sys
import os
from pathlib import Path

# Ensure we can import from tools
sys.path.append(str(Path(__file__).resolve().parent))

from tools.chat import convert_to_search_tags

input_text = """Job Title: Data Scientist
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

Salary Range: Competitive, typically mid‑100k to 200k+ based on experience and level."""

print("Running convert_to_search_tags...")
try:
    tags = convert_to_search_tags(input_text)
    print("\nResult Tags:")
    print(tags)
except Exception as e:
    print(f"\nCaught Exception: {e}")
