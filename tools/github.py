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

# --- Concurrency control ---
CONCURRENT_DOC_FETCH = 3  # limit concurrent doc fetches to avoid rate-limit

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

async def fetch_repo_documentation(repo_full_name: str, headers: dict, client: httpx.AsyncClient) -> str:
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
            for res in results:
                if not isinstance(res, Exception):
                    doc_text += "\n\n" + res
    except Exception as e:
        logger.error(f"Error fetching repository contents for {repo_full_name}: {e}")
    readme = await readme_task
    if readme:
        doc_text = "# README\n" + readme + doc_text
    return doc_text if doc_text.strip() else "No documentation available."

async def fetch_simple_metadata(repo_full_name: str, headers: dict, client: httpx.AsyncClient) -> dict:
    meta = {"branch_count": 0, "pr_count": 0}
    try:
        b_url = f"https://api.github.com/repos/{repo_full_name}/branches?per_page=6"
        b_resp = await mcp_adapter.fetch(b_url, headers=headers, client=client)
        if b_resp.status_code == 200:
            meta["branch_count"] = len(b_resp.json())
        p_url = f"https://api.github.com/repos/{repo_full_name}/pulls?state=all&per_page=11"
        p_resp = await mcp_adapter.fetch(p_url, headers=headers, client=client)
        if p_resp.status_code == 200:
            meta["pr_count"] = len(p_resp.json())
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
    pages_to_fetch = random.sample(range(1, num_pages + 1), k=min(max_pages_per_run, num_pages))

    async with httpx.AsyncClient(timeout=30.0) as client:
        for page in pages_to_fetch:
            params = {
                "q": query,
                "per_page": per_page,
                "page": page
            }
            if sort_by_stars:
                params.update({
                    "sort": "stars",
                    "order": "desc"
                })

            try:
                response = await client.get(url, headers=headers, params=params)
                
                # Simple retry for rate limits
                if response.status_code in [403, 429]:
                    logger.warning(f"Rate limit hit ({response.status_code}). Backing off for 10s...")
                    await asyncio.sleep(10)
                    response = await client.get(url, headers=headers, params=params)

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

                    repositories.append({
                        "title": repo.get("name", "No title available"),
                        "link": repo_link,
                        "clone_url": clone_url,
                        "combined_doc": doc if not isinstance(doc, Exception) else "",
                        "stars": repo.get("stargazers_count", 0),
                        "full_name": full_name,
                        "open_issues_count": repo.get("open_issues_count", 0),
                        "size": repo.get("size", 0),
                        "contributors_count": 1,
                        "file_list": [],
                        "branch_count": 0,
                        "pr_count": 0,
                        "license_name": license_info.get("name", "Unknown"),
                        "license_key": license_info.get("key", "unknown")
                    })

            except Exception as e:
                logger.error(f"Error fetching repositories for query '{query}': {e}")
                continue

    logger.info(f"Fetched {len(repositories)} repositories for query '{query}'.")
    return repositories

async def ingest_github_repos_async(state, config) -> dict:
    headers = {
        "Authorization": f"token {os.getenv('GITHUB_API_KEY')}",
        "Accept": "application/vnd.github.v3+json"
    }

    # Extract keywords from searchable_query
    keyword_list = [kw.strip() for kw in state.searchable_query.split(":") if kw.strip()]
    logger.info(f"Searchable keywords (raw): {keyword_list}")

    target_language = "python"
    filtered_keywords = []
    for kw in keyword_list:
        if kw.startswith("target-"):
            target_language = kw.split("target-")[-1]
        else:
            filtered_keywords.append(kw)
    keyword_list = filtered_keywords

    project_type = getattr(state, "project_type", "All")
    logger.info(f"Filtered keywords: {keyword_list} | Target language: {target_language} | Project Type: {project_type}")
    
    star_filter = ""
    if project_type == "Personal Project":
        star_filter = " stars:0..100 -topic:template -topic:boilerplate -topic:starter-kit" 
    elif project_type == "Industry Standard":
        star_filter = " stars:>5000"
    
    from agent import AgentConfiguration
    agent_config = AgentConfiguration.from_runnable_config(config)

    all_repos = []
    semaphore = asyncio.Semaphore(CONCURRENT_DOC_FETCH)
    tasks = []

    async def fetch_with_sem(sem, q):
        async with sem:
            return await fetch_github_repositories(q, agent_config.max_results, agent_config.per_page, headers)

    for keyword in keyword_list:
        # Relax: "auto-insurance-domain" -> "auto insurance domain" (matches text in README/desc)
        clean_kw = keyword.replace("-", " ")
        query = f"{clean_kw} language:{target_language}{star_filter}"
        tasks.append(asyncio.create_task(fetch_with_sem(semaphore, query)))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if not isinstance(result, Exception):
            all_repos.extend(result)
        else:
            logger.error(f"Error in fetching repositories for a keyword: {result}")

    # Remove duplicates
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
