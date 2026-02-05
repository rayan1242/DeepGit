import os
import logging
import subprocess
import shutil
import uuid
from pathlib import Path
import httpx

logger = logging.getLogger(__name__)

class GitHubActionError(Exception):
    pass

def create_github_repo(repo_name: str, token: str) -> str:
    """
    Creates a new private repository on the authenticated user's GitHub account.
    Returns the clone URL of the new repository.
    """
    url = "https://api.github.com/user/repos"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "name": repo_name,
        "private": True,  # Default to private for safety
        "description": "Forked/Mirrored via DeepGit",
        "has_issues": True,
        "has_projects": False,
        "has_wiki": False
    }
    
    try:
        response = httpx.post(url, headers=headers, json=data)
        if response.status_code == 201:
            repo_data = response.json()
            logger.info(f"Successfully created repository: {repo_data['html_url']}")
            return repo_data['clone_url']
        elif response.status_code == 422: # Unprocessable Entity - likely repo already exists
             logger.warning(f"Repository {repo_name} might already exist.")
             # Try to construct the URL assuming it exists on the user's account
             # We need the user's login name to verify, but we can try to return a constructed URL or fail.
             # For now, let's try to get the user info to construct the URL.
             user_resp = httpx.get("https://api.github.com/user", headers=headers)
             if user_resp.status_code == 200:
                 username = user_resp.json()['login']
                 return f"https://github.com/{username}/{repo_name}.git"
             else:
                 raise GitHubActionError(f"Repo exists/invalid name and cannot fetch username: {response.text}")
        else:
            raise GitHubActionError(f"Failed to create GitHub repo: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Network error creating repo: {e}")
        raise GitHubActionError(f"Network error creating repo: {e}")

def clone_and_push_repo(source_url: str, target_repo_name: str, token: str) -> str:
    """
    Clones a source repository and pushes it to a new destination on the user's GitHub.
    
    1. Create new repo on user's GitHub.
    2. Clone source repo to temporary dir.
    3. Remove origin remote.
    4. Add new origin remote (authenticated).
    5. Push to new origin.
    6. Cleanup.
    
    Returns the URL of the new repository.
    """
    # Create unique temp directory
    temp_dir = Path(f"temp_clone_{uuid.uuid4()}")
    
    try:
        # 1. Create Repo
        target_clone_url = create_github_repo(target_repo_name, token)
        
        # Insert token into target URL for authentication
        # target_clone_url usually looks like https://github.com/User/Repo.git
        if "https://" in target_clone_url:
            auth_target_url = target_clone_url.replace("https://", f"https://{token}@")
        else:
            auth_target_url = target_clone_url # fallback or SSH
            
        logger.info(f"Cloning from {source_url}...")
        
        # 2. Clone
        subprocess.run(
            ["git", "clone", source_url, str(temp_dir)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # 3. Change Remote
        cwd = str(temp_dir)
        subprocess.run(
            ["git", "remote", "remove", "origin"],
            cwd=cwd,
            check=True
        )
        subprocess.run(
            ["git", "remote", "add", "origin", auth_target_url],
            cwd=cwd,
            check=True
        )
        
        # 4. Push
        logger.info(f"Pushing to {target_clone_url}...")
        subprocess.run(
            ["git", "push", "-u", "origin", "main"], # Try main first
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        # Note: If main doesn't exist (e.g. master), this might fail. 
        # A more robust way is to push --all or check branch name. 
        # Retrying with --all
        subprocess.run(
            ["git", "push", "--all", "origin"],
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        return target_clone_url

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else str(e)
        logger.error(f"Git operation failed: {error_msg}")
        raise GitHubActionError(f"Git operation failed: {error_msg}")
    except Exception as e:
        logger.error(f"Unexpected error in clone_and_push: {e}")
        raise e
    finally:
        # 5. Cleanup
        if temp_dir.exists():
            try:
                # On Windows, readonly files (like .git/objects) can cause rmtree to fail.
                # We need a handler to force delete.
                def on_rm_error(func, path, exc_info):
                    os.chmod(path, 0o777)
                    func(path)
                    
                shutil.rmtree(temp_dir, onerror=on_rm_error)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp dir {temp_dir}: {e}")
