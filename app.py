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
import auth  # New Auth Module
from database import init_db

# Initialize DB on startup
init_db()

def update_auth_status():
    token = auth.get_active_token()
    if token:
        username = auth.get_active_username() or "Unknown"
        return f"✅ Logged in as: **{username}**"
    return "❌ Not Logged In (Using Rate-Limited IP)"

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
99: • Query Expansion&nbsp;→&nbsp;ColBERT‑v2 token‑level Semantic Retrieval&nbsp;→&nbsp;Cross‑Encoder Re‑ranking<br/>
100: • Hardware‑aware Dependency Filter that discards repos your device can’t run<br/>
101: • Codebase & Community Insight modules for quality and activity signals<br/><br/>
102: Feed it a topic below; the agent will analyze, rank, and explain the most relevant, <em>runnable</em> repositories.  
103: A short wait earns you a gold‑curated list.
104: </p>"""


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
    token = auth.get_active_token()
    initial_state = {
        "user_query": topic,
        "project_type": project_type,
        "target_industry": industry,
        "skip_llm_expansion": skip_llm,
        "github_token": token or ""
    }
    result = graph.invoke(initial_state)
    result_container["raw_result"] = result.get("final_results", "No results returned.")
    result_container["structured_results"] = result.get("structured_results", [])

def stream_workflow(topic, project_type="All", industry="", skip_llm=False):
    # Enforce Authentication
    if not auth.get_active_token():
        yield "❌ Authentication Required", "Please connect your GitHub account in the settings above to continue.", []
        return

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
        
        # --- Auth UI ---
        auth_status_display = gr.Markdown(update_auth_status())

        with gr.Accordion("🔐 GitHub Authentication (Settings)", open=False):
            gr.Markdown("Connect your GitHub account to bypass rate limits **(5000 requests/hour)** and enable repository cloning.")
            
            with gr.Row():
                client_id_input = gr.Textbox(label="GitHub Client ID", value=auth.get_client_id() or "", placeholder="Paste your OAuth App Client ID here")
                save_client_id_btn = gr.Button("Save Client ID")
            
            save_status = gr.Markdown("")
            save_client_id_btn.click(lambda x: (auth.set_client_id(x), "✅ Client ID Saved!")[1], inputs=[client_id_input], outputs=[save_status])
            
            with gr.Row():
                auth_btn = gr.Button("Connect GitHub Account", variant="primary")
                logout_btn = gr.Button("Logout")
            
            auth_message = gr.Markdown("")
            auth_link_display = gr.Markdown("")
            device_code_state = gr.State()
            
            # Polling Logic for UI
            def on_auth_click():
                res = auth.initiate_device_flow()
                if "error" in res:
                    return f"❌ Error: {res['error']}", "", None
                
                msg = f"### Step 1: Authorization Required\n\n**User Code:** `{res['user_code']}`\n\n1. Copy the code above.\n2. Click the link below to open GitHub.\n3. Paste the code and authorize DeepGit."
                link = f"[👉 Click here to Authorize on GitHub]({res['verification_uri']})"
                return msg, link, res['device_code']

            auth_btn.click(on_auth_click, outputs=[auth_message, auth_link_display, device_code_state])
            
            check_auth_btn = gr.Button("I have authorized the app")
            
            def on_check_auth(device_code):
                if not device_code:
                     return "❌ Please click 'Connect GitHub Account' first.", update_auth_status()
                # Attempt to get token (short check)
                token = auth.poll_for_token(device_code, interval=2, timeout=5) 
                if token:
                    return "✅ Success! You are logged in.", update_auth_status()
                return "❌ Authorization pending. Determine if you approved the request in browser, then click again.", update_auth_status()

            check_auth_btn.click(on_check_auth, inputs=[device_code_state], outputs=[auth_message, auth_status_display])
            
            # Logout
            def on_logout():
                auth.logout()
                return "Logged out.", "", update_auth_status()

            logout_btn.click(on_logout, outputs=[auth_message, auth_link_display, auth_status_display])
        # --- End Auth UI ---

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
            source_url = repo['clone_url']
            
            # Use authenticated token
            token = auth.get_active_token()
            if not token:
                return "❌ Error: Please login via 'GitHub Authentication' first."
            
            # License Check (Relaxed)
            # allowed_licenses = ['mit', 'apache-2.0', 'bsd-3-clause', 'bsd-2-clause', 'unlicense', 'cc0-1.0']
            # license_key = repo.get('license_key', 'unknown').lower()
            # if license_key not in allowed_licenses and license_key != 'unknown' and license_key != 'none':
            #    return f"⚠️ **Action Blocked**: This repo has a restricted license ('{repo.get('license_name')}')."
            
            # Allow all, just warn if restricted? No, user explicitly asked to allow unknown.
            # We just proceed.

            new_url = clone_and_push_repo(source_url, target_name, token, private=False)
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

    def stepwise_runner_direct_tag(topic, p_type, ind, current_repos):
        # Runs with skip_llm=True so we don't re-generate tags
        for status, details, structured in stream_workflow(topic, p_type, ind, skip_llm=True):
            # If structured is empty (intermediate step), yield current_repos to preserve state
            # causing the UI to not break/flash empty.
            if not structured:
                yield status, details, current_repos
            else:
                yield status, details, structured

    from tools.chat import iterative_convert_to_search_tags

    # Hidden state to store tags for automatic execution
    tags_string_state = gr.State("")

    def on_generate_tags_auto(topic):
        try:
             # iterative_convert_to_search_tags returns a colon-separated string
             tags_string = iterative_convert_to_search_tags(topic)
             if not tags_string:
                 return "None"
             return tags_string
        except Exception as e:
             logger.error(f"Tag generation failed: {e}")
             return "Error"

    # Chain: Generate Tags -> Store in State -> Trigger Search
    search_btn.click(
        fn=on_generate_tags_auto,
        inputs=[research_input],
        outputs=[tags_string_state]
    ).then(
        fn=stepwise_runner_direct_tag,
        inputs=[tags_string_state, project_type_input, industry_input, state],
        outputs=[status_display, detail_display, state],
        show_progress=True
    ).then(fn=update_dropdown, inputs=[state], outputs=[repo_dropdown])

    # Connect enter key on text box to same function chain
    # research_input.submit(...) # (Optional, matching button behavior)

    gr.HTML(footer)
demo.queue(max_size=10).launch()
