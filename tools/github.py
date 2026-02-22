# tools/github.py
import os
import base64
import logging
import asyncio
from pathlib import Path
import httpx
import random
from tools.mcp_adapter import mcp_adapter  # Import MCP adapter

logger = logging.getLogger(__name__)

# In-memory cache to store file content for given URLs
FILE_CONTENT_CACHE = {}

# --- Concurrency control & Doc Size Limits ---
CONCURRENT_DOC_FETCH = 3  # limit concurrent doc fetches to avoid rate-limit
MAX_README_SIZE = 500    # Max README size in bytes (~1000 tokens)
MAX_ARCH_DOCS_SIZE = 500 # Max architecture/other docs size in bytes (~1250 tokens)
MAX_TOTAL_DOC_SIZE = 1000 # Max total doc size per repo in bytes (~2000 tokens)

async def fetch_readme_content(repo_full_name: str, headers: dict, client: httpx.AsyncClient) -> str:
    readme_url = f"https://api.github.com/repos/{repo_full_name}/readme"
    try:
        response = await mcp_adapter.fetch(readme_url, headers=headers, client=client)
        if response.status_code == 200:
            readme_data = response.json()
            content = readme_data.get('content', '')
            if content:
                return base64.b64decode(content).decode('utf-8')
    except Exception as e:
        logger.error(f"Error fetching README for {repo_full_name}: {e}")
    return ""

async def fetch_file_content(download_url: str, client: httpx.AsyncClient) -> str:
    if download_url in FILE_CONTENT_CACHE:
        return FILE_CONTENT_CACHE[download_url]
    try:
        response = await mcp_adapter.fetch(download_url, client=client)
        if response.status_code == 200:
            text = response.text
            FILE_CONTENT_CACHE[download_url] = text
            return text
    except Exception as e:
        logger.error(f"Error fetching file from {download_url}: {e}")
    return ""

async def fetch_directory_markdown(repo_full_name: str, path: str, headers: dict, client: httpx.AsyncClient) -> str:
    md_content = ""
    url = f"https://api.github.com/repos/{repo_full_name}/contents/{path}"
    try:
        response = await mcp_adapter.fetch(url, headers=headers, client=client)
        if response.status_code == 200:
            items = response.json()
            tasks = []
            for item in items:
                if item["type"] == "file" and item["name"].lower().endswith(".md"):
                    tasks.append(fetch_file_content(item["download_url"], client))
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for item, content in zip(items, results):
                    if item["type"] == "file" and item["name"].lower().endswith(".md") and not isinstance(content, Exception):
                        md_content += f"\n\n# {item['name']}\n" + content
    except Exception as e:
        logger.error(f"Error fetching directory markdown for {repo_full_name}/{path}: {e}")
    return md_content

async def fetch_repo_documentation(repo_full_name: str, headers: dict, client: httpx.AsyncClient) -> tuple:
    """
    Fetch and truncate repository documentation to respect size limits.
    
    Returns:
        tuple: (final_doc, readme_size, arch_doc_size)
    """
    doc_text = ""
    readme_task = asyncio.create_task(fetch_readme_content(repo_full_name, headers, client))
    root_url = f"https://api.github.com/repos/{repo_full_name}/contents"
    try:
        response = await mcp_adapter.fetch(root_url, headers=headers, client=client)
        if response.status_code == 200:
            items = response.json()
            tasks = []
            semaphore = asyncio.Semaphore(CONCURRENT_DOC_FETCH)

            async def safe_fetch(task_func, *args):
                async with semaphore:
                    return await task_func(*args)

            for item in items:
                if item["type"] == "file" and item["name"].lower().endswith(".md") and item["name"].lower() != "readme.md":
                    tasks.append(asyncio.create_task(safe_fetch(fetch_file_content, item["download_url"], client)))
                elif item["type"] == "dir" and item["name"].lower() in ["docs", "documentation"]:
                    tasks.append(asyncio.create_task(safe_fetch(fetch_directory_markdown, repo_full_name, item["name"], headers, client)))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Accumulate docs while respecting size limits
            for res in results:
                if not isinstance(res, Exception) and res:
                    # Check if adding this would exceed limit
                    new_size = len(doc_text) + len(res) + 4  # +4 for "\n\n" separator
                    if new_size <= MAX_ARCH_DOCS_SIZE:
                        doc_text += "\n\n" + res
                    else:
                        # Truncate this doc to fit remaining space
                        remaining = MAX_ARCH_DOCS_SIZE - len(doc_text) - 4
                        if remaining > 100:  # Only add if at least 100 bytes remain
                            truncated_size = len(res)
                            doc_text += "\n\n" + res[:remaining] + "\n[... truncated]"
                            logger.info(f"Architecture docs for {repo_full_name} truncated from {truncated_size} to {remaining} bytes")
                        break
    except Exception as e:
        logger.error(f"Error fetching repository contents for {repo_full_name}: {e}")
    
    readme = await readme_task
    
    # Truncate README if it exceeds limit
    if readme and len(readme) > MAX_README_SIZE:
        logger.info(f"README for {repo_full_name} truncated from {len(readme)} to {MAX_README_SIZE} bytes")
        readme = readme[:MAX_README_SIZE] + "\n[... truncated]"
    
    readme_size = len(readme) if readme else 0
    arch_doc_size = len(doc_text)

    # Build final doc, respecting total size limit
    if readme:
        combined = "# README\n" + readme + "\n\n" + doc_text
    else:
        combined = doc_text
    
    # Final truncation if necessary
    if len(combined) > MAX_TOTAL_DOC_SIZE:
        logger.info(f"Total docs for {repo_full_name} truncated from {len(combined)} to {MAX_TOTAL_DOC_SIZE} bytes")
        combined = combined[:MAX_TOTAL_DOC_SIZE] + "\n[... content truncated to size limit]"
    
    final_doc = combined if combined.strip() else "No documentation available."
    return final_doc, readme_size, arch_doc_size

# async def fetch_simple_metadata(repo_full_name: str, headers: dict, client: httpx.AsyncClient) -> dict:
#     meta = {"branch_count": 0, "pr_count": 0}
#     try:
#         b_url = f"https://api.github.com/repos/{repo_full_name}/branches?per_page=6"
#         b_resp = await mcp_adapter.fetch(b_url, headers=headers, client=client)
#         if b_resp.status_code == 200:
#             meta["branch_count"] = len(b_resp.json())
#         p_url = f"https://api.github.com/repos/{repo_full_name}/pulls?state=all&per_page=11"
#         p_resp = await mcp_adapter.fetch(p_url, headers=headers, client=client)
#         if p_resp.status_code == 200:
#             meta["pr_count"] = len(p_resp.json())
#     except Exception as e:
#         logger.error(f"Error fetching metadata for {repo_full_name}: {e}")
#     return meta


async def fetch_simple_metadata(repo_full_name: str, headers: dict, client: httpx.AsyncClient) -> dict:
    meta = {
        "branch_count": 0,
        "pr_count": 0,
        "contributors_count": 0,
        "commit_count": 0
    }

    try:
        # Branches
        b_url = f"https://api.github.com/repos/{repo_full_name}/branches?per_page=100"
        b_resp = await mcp_adapter.fetch(b_url, headers=headers, client=client)
        if b_resp.status_code == 200:
            meta["branch_count"] = len(b_resp.json())

        # Pull Requests
        p_url = f"https://api.github.com/repos/{repo_full_name}/pulls?state=all&per_page=100"
        p_resp = await mcp_adapter.fetch(p_url, headers=headers, client=client)
        if p_resp.status_code == 200:
            meta["pr_count"] = len(p_resp.json())

        # Contributors
        c_url = f"https://api.github.com/repos/{repo_full_name}/contributors?per_page=100"
        c_resp = await mcp_adapter.fetch(c_url, headers=headers, client=client)
        if c_resp.status_code == 200:
            meta["contributors_count"] = len(c_resp.json())

        # Commits
        commits_url = f"https://api.github.com/repos/{repo_full_name}/commits?per_page=200"
        commits_resp = await mcp_adapter.fetch(commits_url, headers=headers, client=client)
        if commits_resp.status_code == 200:
            meta["commit_count"] = len(commits_resp.json())

    except Exception as e:
        logger.error(f"Error fetching metadata for {repo_full_name}: {e}")

    return meta



async def fetch_github_repositories(
    query: str,
    max_results: int,
    per_page: int,
    headers: dict,
    max_pages_per_run: int = 4,
    sort_by_stars: bool = False
) -> list:
    """
    Fetch GitHub repositories for a query.
    - Randomizes pages to improve uniqueness.
    - Limits pages fetched per run to avoid API rate limits.
    - Can optionally remove 'sort by stars' to get more diverse repos.
    """
    url = "https://api.github.com/search/repositories"
    repositories = []

    # Determine number of pages needed
    num_pages = max_results // per_page
    if max_results % per_page != 0:
        num_pages += 1

    # Randomly sample pages
    # pages_to_fetch = random.sample(range(1, num_pages + 1), k=min(max_pages_per_run, num_pages))
    pages_to_fetch = range(1, num_pages + 1)

    async with httpx.AsyncClient(timeout=30.0) as client:
        for page in pages_to_fetch:
            params = {
                "q": query,
                "per_page": per_page,
                "page": page
            }
            # if sort_by_stars:
            #     params.update({
            #         "sort": "stars",
            #         "order": "desc"
            #     })

            try:
                # Use mcp_adapter.fetch instead of client.get to ensure correct headers/auth handling
                response = await mcp_adapter.fetch(url, headers=headers, params=params, client=client)
                
                # Simple retry for rate limits
                if response.status_code in [403, 429]:
                    logger.warning(f"Rate limit hit ({response.status_code}). Backing off for 10s...")
                    await asyncio.sleep(10)
                    response = await mcp_adapter.fetch(url, headers=headers, params=params, client=client)

                if response.status_code != 200:
                    logger.error(f"Error {response.status_code}: {response.json().get('message')}")
                    # Stop fetching pages if blocked
                    if response.status_code in [403, 429]:
                        break
                    continue

                items = response.json().get("items", [])
                if not items:
                    continue

                # Optionally fetch docs or further info for each repo
                tasks = []
                for repo in items:
                    full_name = repo.get("full_name", "")
                    # Placeholder for fetching combined documentation if needed
                    tasks.append(asyncio.create_task(fetch_repo_documentation(full_name, headers, client)))

                docs = await asyncio.gather(*tasks, return_exceptions=True)

                for repo, doc in zip(items, docs):
                    repo_link = repo.get("html_url", "")
                    full_name = repo.get("full_name", "")
                    clone_url = repo.get("clone_url", f"https://github.com/{full_name}.git")
                    license_info = repo.get("license") or {}

                    if isinstance(doc, Exception):
                        combined_doc = ""
                        readme_size = 0
                        arch_size = 0
                    else:
                        combined_doc, readme_size, arch_size = doc
                    
                    repositories.append({
                        "title": repo.get("name", "No title available"),
                        "link": repo_link,
                        "clone_url": clone_url,
                        "combined_doc": combined_doc,
                        "readme_size": readme_size,
                        "arch_size": arch_size,
                        "stars": repo.get("stargazers_count", 0),
                        "full_name": full_name,
                        "open_issues_count": repo.get("open_issues_count", 0),
                        "size": repo.get("size", 0),
                        # "contributors_count": 1,
                        "file_list": [],
                        # "branch_count": 0,
                        # "pr_count": 0,
                        "license_name": license_info.get("name", "Unknown"),
                        "license_key": license_info.get("key", "unknown")
                    })

            except Exception as e:
                logger.error(f"Error fetching repositories for query '{query}': {e}")
                continue

    logger.info(f"Fetched {len(repositories)} repositories for query '{query}'.")
    return repositories

async def ingest_github_repos_async(state, config) -> dict:
    # Prioritize User Token (OAuth) if available, otherwise use Env Var
    token = getattr(state, "github_token", "")  # or os.getenv("GITHUB_API_KEY")
    
    headers = {
        "Accept": "application/vnd.github.v3+json"
    }
    if token:
        headers["Authorization"] = f"token {token}"

    # Extract queries
    # New multi-agent flow provides a list of query combos found in state.searchable_queries
    # Old flow provided a single string in state.searchable_query
    query_combos = getattr(state, "searchable_queries", [])
    if not query_combos:
        # Fallback to old behavior: treat the single string as a list of 1 (or split if it was colon separated?)
        # Actually, the old behavior split by colon and did OR search. 
        # But if convert_query is updated, it populates searchable_queries.
        # If not, we might be in legacy state.
        raw_q = getattr(state, "searchable_query", "")
        if raw_q:
            # If it's legacy colon-separated list of single keywords, we treat them as separate queries
            query_combos = [kw.strip() for kw in raw_q.split(":") if kw.strip()]

    logger.info(f"Processing {len(query_combos)} query combinations: {query_combos}")

    project_type = getattr(state, "project_type", "All")
    
    # Filter for stars
    star_filter = " stars:>5"
    if project_type == "Personal Project":
        star_filter = " stars:5..500" 
    
    from agent import AgentConfiguration
    agent_config = AgentConfiguration.from_runnable_config(config)

    all_repos = []
    
    # Log token status (masked)
    if token:
        logger.info(f"Using GitHub Token: {token[:4]}...{token[-4:]}")
    else:
        logger.warning("No GitHub Token found! Rate limits will be very strict (10 req/min).")

    search_requests = []
    for combo in query_combos:
        # Combo is like "auto-insurance:cost-prediction:target-python"
        parts = [p.strip() for p in combo.split(":") if p.strip()]
        
        target_language = None
        search_terms = []
        
        for p in parts:
            if p.startswith("target-"):
                target_language = p.split("target-")[-1]
            else:
                search_terms.append(p)
        
        # User requested OR logic instead of AND.
        # So we iterate over each search term and run a separate query.
        for term in search_terms:
            full_query = f"{term}{star_filter}"
            if target_language:
                full_query += f" language:{target_language}"
            search_requests.append(full_query)

    # SEQUENTIAL EXECUTION to avoid hitting 30 req/min Search API limit
    # (5 tags * parallel would be ~5-10 burst requests, risking 403)
    for i, full_query in enumerate(search_requests):
        logger.info(f"Executing Search {i+1}/{len(search_requests)}: '{full_query}'")
        try:
            # Run search for this tag
            result = await fetch_github_repositories(full_query, agent_config.max_results, agent_config.per_page, headers)
            all_repos.extend(result)
            
            # Short sleep between searches to be nice to the API
            if i < len(search_requests) - 1:
                await asyncio.sleep(3.0)
                
        except Exception as e:
            logger.error(f"Error fetching repositories for query '{full_query}': {e}")

    # Deduplicate
    seen = set()
    unique_repos = []
    for repo in all_repos:
        if repo["full_name"] not in seen:
            seen.add(repo["full_name"])
            unique_repos.append(repo)
    state.repositories = unique_repos
    
    # Enrichment for Personal Projects
    if project_type == "Personal Project":
        logger.info(f"Enriching {len(unique_repos)} repos with Branch/PR metadata...")
        enrich_tasks = []
        async with httpx.AsyncClient() as client:
            for repo in unique_repos:
                enrich_tasks.append(fetch_simple_metadata(repo["full_name"], headers, client))
            enrich_results = await asyncio.gather(*enrich_tasks, return_exceptions=True)
            
            for repo, meta in zip(unique_repos, enrich_results):
                if isinstance(meta, dict):
                    repo.update(meta)
    
    logger.info(f"Total unique repositories fetched: {len(state.repositories)}")
    return {"repositories": state.repositories}


def ingest_github_repos(state, config):
    return asyncio.run(ingest_github_repos_async(state, config))
