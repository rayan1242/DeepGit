import time
import requests
import logging
from database import set_config, get_config, delete_config

logger = logging.getLogger(__name__)

# --- Configuration ---
SCOPE = "repo read:user"
AUTH_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"

# --- Client ID Management ---
# We store the user's Client ID in the database.
# If not set, we cannot authenticate.

def get_client_id():
    return get_config("github_client_id")

def set_client_id(client_id):
    set_config("github_client_id", client_id.strip())

def initiate_device_flow():
    """
    Step 1: Request a device code from GitHub.
    Returns: dict with verification_uri, user_code, etc. OR None on error.
    """
    client_id = get_client_id()
    if not client_id:
        logger.error("No GitHub Client ID configured.")
        return {"error": "Missing Client ID. Please configure it in Settings."}

    try:
        response = requests.post(
            AUTH_URL,
            data={"client_id": client_id, "scope": SCOPE},
            headers={"Accept": "application/json"}
        )
        if response.status_code != 200:
             logger.error(f"GitHub Auth Error {response.status_code}: {response.text}")
             return {"error": f"GitHub API Error: {response.text}"}
             
        data = response.json()
        
        if "error" in data:
            logger.error(f"Device flow error: {data['error_description']}")
            return {"error": data['error_description']}
            
        return {
            "verification_uri": data.get("verification_uri"),
            "user_code": data.get("user_code"),
            "interval": data.get("interval", 5),
            "device_code": data.get("device_code"),
            "expires_in": data.get("expires_in")
        }
    except Exception as e:
        logger.error(f"Failed to initiate device flow: {e}")
        return {"error": str(e)}

def poll_for_token(device_code, interval=5, timeout=900):
    """
    Step 2: Poll GitHub for the access token.
    Blocks until user authorizes or code expires or timeout.
    """
    client_id = get_client_id()
    if not client_id:
        return None
        
    elapsed = 0
    # timeout is now an argument
    
    while elapsed < timeout:
        time.sleep(interval)
        elapsed += interval
        
        try:
            response = requests.post(
                TOKEN_URL,
                data={
                    "client_id": client_id,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
                },
                headers={"Accept": "application/json"}
            )
            data = response.json()
            
            error = data.get("error")
            if error == "authorization_pending":
                continue
            elif error == "slow_down":
                interval += 5
                continue
            elif error == "expired_token":
                logger.error("Device code expired.")
                return None
            elif "access_token" in data:
                # Success!
                token = data["access_token"]
                set_config("github_token", token)
                
                # Fetch username
                user_info = get_user_info(token)
                if user_info:
                    username = user_info.get("login", "Unknown")
                    set_config("github_username", username)
                    logger.info(f"Successfully logged in as {username}")
                
                return token
            else:
                logger.error(f"Polling error: {data}")
                return None
                
        except Exception as e:
            logger.error(f"Polling exception: {e}")
            
    return None

def get_user_info(token):
    try:
        response = requests.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json"
            }
        )
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None

def get_active_token():
    """Retrieve the stored token."""
    return get_config("github_token")

def get_active_username():
    """Retrieve stored username."""
    return get_config("github_username")

def logout():
    """Clear stored credentials."""
    delete_config("github_token")
    delete_config("github_username")
