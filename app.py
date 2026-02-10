import gradio as gr
import os
import json
import time
import threading
import logging
import subprocess
from agent import graph  # Your DeepGit langgraph workflow
from tools.github_actions import clone_and_push_repo
from tools.resume_generator import generate_resume_bullets
from tools.feature_recommender import recommend_features

# ---------------------------
# Set environment variables to prevent thread/multiprocessing issues on macOS/Linux
# os.environ["TOKENIZERS_PARALLELISM"] = "false"
# os.environ["OMP_NUM_THREADS"] = "1"
# os.environ["MKL_NUM_THREADS"] = "1"
# ---------------------------



# ---------------------------
# Global Logging Buffer Setup
# ---------------------------
LOG_BUFFER = []
LOG_BUFFER_LOCK = threading.Lock()

class BufferLogHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        with LOG_BUFFER_LOCK:
            LOG_BUFFER.append(log_entry)

# Attach the custom logging handler if not already attached.
root_logger = logging.getLogger()
if not any(isinstance(h, BufferLogHandler) for h in root_logger.handlers):
    handler = BufferLogHandler()
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

# ---------------------------
# Helper to Filter Log Messages
# ---------------------------
def filter_logs(logs):
    """
    Processes a list of log messages so that any log containing
    "HTTP Request:" is replaced with a generic message, and adjacent
    HTTP logs are deduplicated.
    """
    filtered = []
    last_was_fetching = False
    for log in logs:
        if "HTTP Request:" in log:
            if not last_was_fetching:
                filtered.append("Fetching repositories...")
                last_was_fetching = True
        else:
            filtered.append(log)
            last_was_fetching = False
    return filtered

# ---------------------------
# Title, Favicon & Description
# ---------------------------
#custom_theme = gr.Theme.load("gstaff/sketch")

favicon_html = """
<head>
<link rel="icon" type="image/x-icon" href="file/assets/deepgit.ico">
<title>DeepGit Research Agent</title>
</head>
"""

title = """
<div style="text-align: center; margin-top: 20px;">
  <h1 style="font-size: 36px; display: inline-flex; align-items: center; gap: 16px;">
    <img src="https://img.icons8.com/?size=100&id=118557&format=png&color=000000" width="64" />
    <span>DeepGit</span>
  </h1>
  <p style="font-size: 18px; color: #555; margin-top: 10px;">
    ⚙️ Built for open-source, by an open-sourcer — DeepGit finds gold in the GitHub haystack.
  </p>
</div>
"""

description = """<p align="center">
<strong>DeepGit</strong> is a multi‑stage research agent that digs through GitHub so you don’t have to.<br/>
Just describe what you’re hunting for — and, if you like, add a hint about your hardware (“GPU‑poor”, “mobile‑only”, etc.).<br/><br/>
Behind the scenes, DeepGit now orchestrates an upgraded tool‑chain:<br/>
• Query Expansion&nbsp;→&nbsp;ColBERT‑v2 token‑level Semantic Retrieval&nbsp;→&nbsp;Cross‑Encoder Re‑ranking<br/>
• Hardware‑aware Dependency Filter that discards repos your device can’t run<br/>
• Codebase & Community Insight modules for quality and activity signals<br/><br/>
Feed it a topic below; the agent will analyze, rank, and explain the most relevant, <em>runnable</em> repositories.  
A short wait earns you a gold‑curated list.
</p>"""


consent_text = """
<div style="padding: 10px; text-align: center;">
  <p>
    By using DeepGit, you consent to the collection and temporary processing of your query for semantic search and ranking purposes.<br/>
    No data is stored permanently, and your input is only used to power the DeepGit agent workflow.
  </p>
  <p>
    ⭐ Star us on GitHub if you find this tool useful!<br/>
    <a href="https://github.com/zamalali/DeepGit" target="_blank">GitHub</a>
  </p>
</div>
"""

footer = """
<div style="text-align: center; margin-top: 40px; font-size: 13px; color: #888;">
    Made with <span style="color: crimson;">❤️</span> by <b>Zamal</b>
</div>
"""

# ---------------------------
# HTML Table Renderer
# ---------------------------
def format_percent(value):
    try:
        return f"{float(value) * 100:.1f}%"
    except:
        return value

def parse_result_to_html(raw_result: str) -> str:
    entries = raw_result.strip().split("Final Rank:")
    html = """
    <style>
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 1em 0;
            font-size: 14px;
        }
        th, td {
            padding: 12px 15px;
            border: 1px solid #ddd;
            text-align: left;
            vertical-align: top;
        }
        th {
            background-color: #f4f4f4;
        }
        tr:hover { background-color: #f9f9f9; }
    </style>
    <table>
        <thead>
            <tr>
                <th>Rank</th>
                <th>Title</th>
                <th>Link</th>
                <th>Semantic Similarity</th>
                <th>Cross-Encoder</th>
                <th>Final Score</th>
            </tr>
        </thead>
        <tbody>
    """
    for entry in entries[1:]:
        lines = entry.strip().split("\n")
        data = {}
        data["Final Rank"] = lines[0].strip()
        for line in lines[1:]:
            if ": " in line:
                key, val = line.split(": ", 1)
                data[key.strip()] = val.strip()
        html += f"""
            <tr>
                <td>{data.get('Final Rank', '')}</td>
                <td>{data.get('Title', '')}</td>
                <td><a href="{data.get('Link', '#')}" target="_blank">GitHub</a></td>
                <td>{format_percent(data.get('Semantic Similarity', ''))}</td>
                <td>{float(data.get('Cross-Encoder Score', 0)):.2f}</td>
                <td>{format_percent(data.get('Final Score', ''))}</td>
            </tr>
        """
    html += "</tbody></table>"
    return html

# ---------------------------
# Background Workflow Runner
# ---------------------------
# ---------------------------
# Background Workflow Runner
# ---------------------------
def run_workflow(topic, project_type, industry, result_container, skip_llm=False):
    """Runs the DeepGit workflow and stores the raw result."""
    initial_state = {
        "user_query": topic,
        "project_type": project_type,
        "target_industry": industry,
        "skip_llm_expansion": skip_llm
    }
    result = graph.invoke(initial_state)
    result_container["raw_result"] = result.get("final_results", "No results returned.")
    result_container["structured_results"] = result.get("structured_results", [])

def stream_workflow(topic, project_type="All", industry="", skip_llm=False):
    # Clear the global log buffer
    with LOG_BUFFER_LOCK:
        LOG_BUFFER.clear()
    result_container = {}
    # Run the workflow in a background thread
    workflow_thread = threading.Thread(target=run_workflow, args=(topic, project_type, industry, result_container, skip_llm))
    workflow_thread.start()
    
    last_index = 0
    # While the background thread is alive or new log messages are available, stream updates.
    while workflow_thread.is_alive() or (last_index < len(LOG_BUFFER)):
        with LOG_BUFFER_LOCK:
            new_logs = LOG_BUFFER[last_index:]
            last_index = len(LOG_BUFFER)
        if new_logs:
            # Filter the logs to replace HTTP request messages.
            filtered_logs = filter_logs(new_logs)
            status_msg = filtered_logs[-1]
            detail_msg = "<br/>".join(filtered_logs)
            yield status_msg, detail_msg, []
        time.sleep(0.5)
    
    workflow_thread.join()
    with LOG_BUFFER_LOCK:
        final_logs = LOG_BUFFER[:]
    filtered_final = filter_logs(final_logs)
    final_status = filtered_final[-1] if filtered_final else "Workflow completed."
    raw_result = result_container.get("raw_result", "No results returned.")
    structured = result_container.get("structured_results", [])
    html_result = parse_result_to_html(raw_result)
    yield "", html_result, structured

# ---------------------------
# App UI Setup
# ---------------------------
#  To change the theme set: theme="gstaff/sketch",
with gr.Blocks(
    theme="gstaff/sketch",
    css="""
        #main_container { margin: auto; max-width: 900px; }
        footer, footer * {
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
            overflow: hidden !important;
        }
    """
) as demo:

    gr.HTML(favicon_html)
    gr.HTML(title)
    gr.HTML(description)

    with gr.Column(elem_id="user_consent_container") as consent_block:
        gr.HTML(consent_text)
        agree_button = gr.Button("I Agree", variant="primary")

    with gr.Column(elem_id="main_container", visible=False) as main_block:
        research_input = gr.Textbox(
            label="Research Topic",
            placeholder="Enter your research topic here, e.g., 'Instruction-based fine-tuning for LLaMA 2 using chain-of-thought prompting in Python.' ",
            lines=3
        )
        with gr.Row():
            project_type_input = gr.Dropdown(
                choices=["All", "Personal Project", "Industry Standard"],
                value="All",
                label="Project Type",
                info="Filter by project scale."
            )
            industry_input = gr.Textbox(
                label="Target Industry (Optional)",
                placeholder="e.g. Finance, Healthcare",
                info="Tailor search tags to a specific domain."
            )
        
        search_btn = gr.Button("Generate Search Tags", variant="primary")
        tags_raw_display = gr.Textbox(label="Generated Tags (Raw)", visible=False, interactive=False)
        tags_radio = gr.Radio(label="Select a Query to Launch DeepGit", visible=False, interactive=True)
        # Display the latest log line as status, and full log stream as details.
        status_display = gr.Markdown("")   
        detail_display = gr.HTML("")
        output_html = gr.HTML()
        state = gr.State([])

    def enable_main():
        return gr.update(visible=False), gr.update(visible=True)

    agree_button.click(fn=enable_main, inputs=[], outputs=[consent_block, main_block], queue=False)

    # Action Handlers
    def on_repo_select(idx, repos):
        if not repos or idx is None:
            return ""
        try:
            repo = repos[idx]
            license_str = repo.get('license_name', 'Unknown')
            return f"Selected: **{repo['title']}** ({repo['link']})\nLicense: **{license_str}**"
        except IndexError:
            return "Invalid selection."

    def on_clone_push(idx, target_name, repos):
        if not repos or idx is None:
            return "Error: No repo selected."
        if not target_name:
            return "Error: Please enter a target repository name."
        
        try:
            repo = repos[idx]
            source_url = repo['clone_url']
            token = os.environ.get("GITHUB_API_KEY")
            if not token:
                return "Error: GITHUB_API_KEY not found in environment."
            
            # License Check
            allowed_licenses = ['mit', 'apache-2.0', 'bsd-3-clause', 'bsd-2-clause', 'unlicense', 'cc0-1.0']
            license_key = repo.get('license_key', 'unknown').lower()
            if license_key not in allowed_licenses:
                return f"⚠️ **Action Blocked**: This repo has a restricted or unknown license ('{repo.get('license_name')}'). DeepGit only clones permissive open-source code (MIT, Apache, BSD, etc.)."

            new_url = clone_and_push_repo(source_url, target_name, token)
            return f"✅ Success! Repo cloned and pushed to: [{new_url}]({new_url})"
        except Exception as e:
            return f"❌ Error: {str(e)}"

    def on_generate_resume(idx, repos):
        if not repos or idx is None:
            return "Error: No repo selected."
        
        try:
            repo = repos[idx]
            bullets = generate_resume_bullets(repo['title'], "", repo['combined_doc'])
            return f"### Resume Bullet Points for {repo['title']}\n\n{bullets}"
        
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def on_recommend_features(idx, repos, query_state):
        if not repos or idx is None:
            return "Error: No repo selected."
        
        try:
            repo = repos[idx]
            # query_state is a dict like {'user_query': '...'}
            user_query = query_state.get('user_query', '') if isinstance(query_state, dict) else str(query_state)
            
            recommendations = recommend_features(repo['title'], repo['combined_doc'], user_query)
            return f"### Interview Feature Recommendations for {repo['title']}\n\nContext: *{user_query}*\n\n{recommendations}"
        except Exception as e:
            return f"❌ Error: {str(e)}"

    def update_dropdown(repos):
        if not repos:
            return gr.update(choices=[], value=None)
        choices = [(f"{r['title']} ({r['stars']} stars)", i) for i, r in enumerate(repos)]
        return gr.update(choices=choices, value=0, visible=True)

    # UI Wiring
    with main_block:
        gr.Markdown("### Actions")
        with gr.Row():
            repo_dropdown = gr.Dropdown(label="Select Repository", choices=[], type="value", visible=False)
            selected_repo_display = gr.Markdown("")
        
        repo_dropdown.change(on_repo_select, inputs=[repo_dropdown, state], outputs=[selected_repo_display])
        
        with gr.Row():
            target_name_input = gr.Textbox(label="Target Repo Name (for Fork/Mirror)", placeholder="my-awesome-fork")
            clone_btn = gr.Button("Clone & Push to GitHub")
        
        clone_status = gr.Markdown("")
        clone_btn.click(on_clone_push, inputs=[repo_dropdown, target_name_input, state], outputs=[clone_status])
        
        with gr.Row():
            resume_btn = gr.Button("Generate Project Description Bullets")
        
        resume_output = gr.Markdown("")
        resume_btn.click(on_generate_resume, inputs=[repo_dropdown, state], outputs=[resume_output])

        with gr.Row():
            feature_btn = gr.Button("Recommend Features", variant="secondary")
        
        feature_output = gr.Markdown("")
        feature_btn.click(on_recommend_features, inputs=[repo_dropdown, state, research_input], outputs=[feature_output])

    def stepwise_runner(topic, p_type, ind):
        for status, details, structured in stream_workflow(topic, p_type, ind, skip_llm=False):
            yield status, details, structured

    def stepwise_runner_direct_tag(topic, p_type, ind):
        # Runs with skip_llm=True so we don't re-generate tags
        for status, details, structured in stream_workflow(topic, p_type, ind, skip_llm=True):
            yield status, details, structured

    from tools.chat import convert_to_search_tags

    def on_generate_tags(topic):
        try:
             results = convert_to_search_tags(topic)
             queries = results.get("queries", [])
             raw_tags = results.get("tags", [])
             tags_text = ", ".join(raw_tags)
             
             if not queries:
                  return gr.update(visible=True, choices=["No tags generated."]), gr.update(visible=True, value="None")
                  
             return (
                 gr.update(visible=True, choices=queries, value=None),
                 gr.update(visible=True, value=tags_text)
             )
        except Exception as e:
             return gr.update(visible=True, choices=[f"Error: {e}"]), gr.update(visible=True, value=f"Error: {e}")

    search_btn.click(fn=on_generate_tags, inputs=[research_input], outputs=[tags_radio, tags_raw_display])
    research_input.submit(fn=on_generate_tags, inputs=[research_input], outputs=[tags_radio, tags_raw_display])

    # Changed: Use stepwise_runner_direct_tag for the radio selection
    tags_radio.change(
        fn=stepwise_runner_direct_tag,
        inputs=[tags_radio, project_type_input, industry_input],
        outputs=[status_display, detail_display, state],
        show_progress=True
    ).then(fn=update_dropdown, inputs=[state], outputs=[repo_dropdown])

    gr.HTML(footer)
demo.queue(max_size=10).launch()

