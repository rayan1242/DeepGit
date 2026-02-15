
import sys
import os
from tools.chat import jd_to_github_search

text = """Copart
Software Engineering Intern
position
Dallas, TX
time
Internship
remote
Onsite
seniority
Intern
Industry Exp.
ftfMaximize your interview chances
Copart is a technology leader and the premier online vehicle auction platform globally, seeking a talented Mobile Developer Intern. The role involves developing and maintaining mobile applications with a focus on integrating AI solutions, particularly in LLM and generative AI, into existing Copart Mobile Apps.
Automotive
E-Commerce
Online Auctions
Shipping
check
H1B Sponsor Likelynote

Insider Connection @Copart
4 email credits available today
note
Discover valuable connections within the company who might provide insights and potential referrals.
Get 3x more responses when you reach out via email instead of LinkedIn.
Beyond your network
N
N
A
A
A
Nikhil Sundaram & 4 connections
From your previous company
from your School
V
S
Vinay Kudithipudi & 1 connections
@Illinois Institute of Technology and...
Find Any Email

Responsibilities
Develop and maintain mobile applications with a focus on AI, LLM, and generative AI integration
Assist in the implementation of machine learning models and AI algorithms within existing Mobile Apps
Contribute to the design and development of AI-powered features using LLMs and generative AI techniques integrated with React Native Mobile Applications
Assist in developing and implementing prompt engineering strategies for LLMs
Collaborate with cross-functional teams to understand project requirements and translate them into technical solutions
Conduct experiments and analyze results to improve AI model performance and integration
Stay up-to-date with the latest advancements in AI, particularly in LLM and generative AI technologies
Contribute to documentation, testing, and deployment of AI-enhanced software mobile applications
Participate in code reviews and follow best practices in software development

Qualification
check
Represents the skills you have
Find out how your skills align with this job's requirements. If anything seems off, you can easily click on the tags to select or unselect skills to reflect your actual expertise.

checkMachine Learning
checkReact Native
checkJavaScript
Natural Language Processing
checkSoftware Design Principles
checkCollaboration
checkDocumentation
Required
Basic understanding of machine learning concepts, particularly in natural language processing and generative AI
Familiarity with front end apps and keen in working on apps based on React JS/React Native
Hands on with JavaScript language and technologies such as React-Native, ReactJS and Node.js
Knowledge with SOAP and Restful Services
Knowledge of data structures, algorithms, and software design principles
"""

print(f"Testing jd_to_github_search with {len(text)} chars of text...")
try:
    result = jd_to_github_search(text)
    print(f"Company: {result['company']}")
    print(f"Role: {result['role']}")
    print(f"Semantic Tags ({len(result['semantic_tags'])}): {result['semantic_tags']}")
    print(f"Search Tokens ({len(result['search_tokens'])}): {result['search_tokens']}")
    print(f"GitHub Queries ({len(result['github_queries'])}):")
    for q in result['github_queries']:
        print(f"- {q}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
