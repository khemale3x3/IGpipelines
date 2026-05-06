
import os
import json
import time
import requests
import csv

# Optional heavy deps: import lazily or fall back so editor/CI doesn't fail
try:
    import pandas as pd
except Exception:
    pd = None

# Selenium is imported lazily inside configure_driver to avoid import-time failures
# but keep sentinels for runtime use
webdriver = None
Options = None
By = None

from datetime import datetime
import itertools
import threading
import sys
import random
try:
    import psutil
except Exception:
    psutil = None
import queue
try:
    from tqdm import tqdm
except Exception:
    tqdm = None
    # Provide a minimal fallback progress context manager when tqdm is unavailable
if tqdm is None:
    class _DummyTqdm:
        def __init__(self, total=0, desc=None, bar_format=None):
            self.total = total
            self.desc = desc
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def update(self, n=1):
            return None
    tqdm = _DummyTqdm
import concurrent.futures

# ==================== CONFIGURATION ====================
class ScraperConfig:
    def __init__(self, *args, **kwargs):
        """Flexible initializer accepting either positional/uppercase-style
        args or lowercase kwargs (used by main.py). Supported keys:
        session_ids / SESSION_IDS, max_workers / MAX_WORKERS, max_posts / MAX_POSTS,
        headless / HEADLESS, input_file / INPUT_FILE, done_file / DONE_FILE,
        test_mode / TEST_MODE, max_test_profiles / MAX_TEST_PROFILES,
        output_dir / OUTPUT_DIR.
        """
        def _get(k, default=None):
            return kwargs.get(k, kwargs.get(k.upper(), default))

        # back-compat: positional first arg is session ids
        if args:
            session_ids = args[0]
        else:
            session_ids = _get('session_ids', _get('SESSION_IDS', []))

        self.SESSION_IDS = session_ids or []
        self.MAX_WORKERS = int(_get('max_workers', _get('MAX_WORKERS', 8)))
        self.MAX_POSTS = int(_get('max_posts', _get('MAX_POSTS', 50)))
        self.HEADLESS = bool(_get('headless', _get('HEADLESS', True)))
        self.INPUT_FILE = _get('input_file', _get('INPUT_FILE', 'data/input.csv'))
        self.DONE_FILE = _get('done_file', _get('DONE_FILE', 'data/inputdone.csv'))
        self.TEST_MODE = bool(_get('test_mode', _get('TEST_MODE', False)))
        self.MAX_TEST_PROFILES = int(_get('max_test_profiles', _get('MAX_TEST_PROFILES', 5)))
        self.OUTPUT_DIR = _get('output_dir', _get('OUTPUT_DIR', 'data/output'))
        self.FORCE_MAX_WORKERS = True
        
        # Target queries for GraphQL responses
        self.TARGET_QUERIES = {
            "profile": "user",
            "timeline": "xdt_api__v1__feed__user_timeline_graphql_connection"
        }

# ==================== GLOBAL STATE ====================
spinner_active = False
spinner_username = ""
stats_lock = threading.Lock()
done_urls_lock = threading.Lock()
session_id_lock = threading.Lock()
session_id_index = 0

# ==================== HELPER FUNCTIONS ====================
def get_next_session_id(config):
    """Round-robin session ID selection for load balancing."""
    global session_id_index
    with session_id_lock:
        session_id = config.SESSION_IDS[session_id_index % len(config.SESSION_IDS)]
        session_id_index += 1
        return session_id

def log_message(message, level="INFO", icon=""):
    """Log a colored message to the console with a timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color = "\033[0m"
    if level == "INFO":
        color = "\033[94m"
    elif level == "SUCCESS":
        color = "\033[92m"
    elif level == "WARNING":
        color = "\033[93m"
    elif level == "ERROR":
        color = "\033[91m"

    ascii_icon = "*"
    if level == "INFO":
        ascii_icon = "i"
    elif level == "SUCCESS":
        ascii_icon = "√"
    elif level == "WARNING":
        ascii_icon = "!"
    elif level == "ERROR":
        ascii_icon = "×"

    try:
        print(f"{color}[{timestamp}] [{ascii_icon}] {message}\033[0m")
    except UnicodeEncodeError:
        print(f"[{timestamp}] [{level}] {message}")

def configure_driver(session_id, config, proxy=None):
    """Configure and create a new Chrome driver instance."""
    # lazy import selenium to avoid module import errors when selenium isn't installed
    from selenium import webdriver
    options = webdriver.ChromeOptions()
    
    # Performance optimizations
    if config.HEADLESS:
        options.add_argument("--headless=new")
    
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-browser-side-navigation")
    options.add_argument("--disable-infobars")
    options.add_argument("--mute-audio")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    
    # Disable images and videos for faster loading
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.videos": 2,
        "profile.default_content_setting_values.notifications": 2
    }
    options.add_experimental_option("prefs", prefs)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

    if proxy:
        options.add_argument(f'--proxy-server={proxy}')

    try:
        driver = webdriver.Chrome(options=options)
        
        # Remove webdriver property
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        driver.execute_cdp_cmd("Network.enable", {})
        driver.execute_cdp_cmd("Page.enable", {})

        if session_id:
            try:
                from urllib.parse import unquote
                sid = unquote(session_id)
            except Exception:
                sid = session_id
            driver.get("https://www.instagram.com/")
            time.sleep(1)
            try:
                driver.add_cookie({
                    "name": "sessionid",
                    "value": sid,
                    "domain": ".instagram.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": True
                })
                log_message(f"Session ID set: ...{str(sid)[-10:]}", level="INFO", icon="🔑")
            except Exception:
                log_message("Warning: could not add session cookie to driver", level="WARNING")
        
        return driver
    except Exception as e:
        log_message(f"Failed to create Chrome driver: {str(e)}", level="ERROR")
        return None

def get_username(url):
    """Extract the username from a given Instagram URL."""
    url = url.strip().rstrip('/')
    username = url.split('/')[-1]
    username = username.split('?')[0]
    return username

def is_private_profile(profile_data):
    """Check if a profile is private based on its data."""
    if not profile_data:
        return True
    try:
        return profile_data["data"]["user"]["is_private"]
    except (KeyError, TypeError):
        return True

def extract_location_data(node):
    """Extract comprehensive location data from post node."""
    location = None
    loc_data = node.get("location")
    
    if loc_data:
        location = {
            "id": loc_data.get("pk") or loc_data.get("id"),
            "name": loc_data.get("name"),
            "lat": loc_data.get("lat") or loc_data.get("latitude"),
            "lng": loc_data.get("lng") or loc_data.get("longitude"),
            "address": loc_data.get("address"),
            "city": loc_data.get("city"),
            "short_name": loc_data.get("short_name"),
            "facebook_places_id": loc_data.get("facebook_places_id")
        }
        
        # Remove None values
        location = {k: v for k, v in location.items() if v is not None}
        
        if location:
            log_message(f"Location found: {location.get('name', 'Unknown')} ({location.get('lat')}, {location.get('lng')})", 
                       level="INFO", icon="📍")
    
    return location

def process_graphql_response(response_body, config):
    """Process a GraphQL response to extract profile and timeline data."""
    data = {"profile_info": None, "reel_info": None}

    if not isinstance(response_body, dict):
        return data

    response_data = response_body.get("data", {})

    if config.TARGET_QUERIES["profile"] in response_data:
        data["profile_info"] = response_body

    if config.TARGET_QUERIES["timeline"] in response_data:
        data["reel_info"] = response_body

    return data

def get_network_responses(driver):
    """Extract network responses from browser logs."""
    logs = driver.get_log("performance")
    responses = []

    for log in logs:
        try:
            log_data = json.loads(log["message"])['message']
            if "Network.response" in log_data["method"] or "Network.responseReceived" in log_data["method"]:
                responses.append(log_data)
        except Exception:
            pass

    return responses

def merge_timeline_data(existing_data, new_data, config):
    """Merge new timeline data with existing data to avoid duplicates."""
    if not existing_data:
        return new_data
    if not new_data:
        return existing_data

    try:
        timeline_key = config.TARGET_QUERIES["timeline"]
        existing_edges = existing_data["data"][timeline_key]["edges"]
        new_edges = new_data["data"][timeline_key]["edges"]

        existing_ids = {edge["node"]["id"] for edge in existing_edges}

        for edge in new_edges:
            if edge["node"]["id"] not in existing_ids:
                existing_edges.append(edge)
                existing_ids.add(edge["node"]["id"])

        existing_data["data"][timeline_key]["edges"] = existing_edges
        return existing_data
    except Exception as e:
        log_message(f"Error merging timeline data: {str(e)}", level="ERROR")
        return existing_data

def scrape_profile(driver, url, config):
    """Scrape a single Instagram profile using Selenium with enhanced scrolling."""
    username = get_username(url)
    log_message(f"Starting scrape: {username}", level="INFO", icon="🔍")

    try:
        driver.execute_cdp_cmd("Network.clearBrowserCache", {})
        driver.get("about:blank")
        driver.execute_cdp_cmd("Network.enable", {})

        driver.get(url)
        time.sleep(random.uniform(2.5, 3.5))

        combined_data = {"profile_info": None, "reel_info": None}
        posts_count = 0
        scroll_attempts = 0
        max_scroll_attempts = 50  # Increased for MAX_POSTS=30
        no_new_posts_count = 0
        
        log_message(f"Target: {config.MAX_POSTS} posts", level="INFO", icon="🎯")

        while scroll_attempts < max_scroll_attempts and posts_count < config.MAX_POSTS:
            try:
                responses = get_network_responses(driver)

                for response in responses:
                    try:
                        if "params" in response and "response" in response["params"]:
                            response_url = response["params"]["response"].get("url", "")

                            if "graphql/query" in response_url:
                                request_id = response["params"].get("requestId")
                                if not request_id:
                                    continue

                                body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
                                response_body = json.loads(body["body"])
                                new_data = process_graphql_response(response_body, config)

                                if new_data["profile_info"]:
                                    combined_data["profile_info"] = new_data["profile_info"]
                                
                                if new_data["reel_info"]:
                                    combined_data["reel_info"] = merge_timeline_data(
                                        combined_data["reel_info"],
                                        new_data["reel_info"],
                                        config
                                    )
                    except Exception as e:
                        continue

                # Count current posts
                current_posts = 0
                if combined_data["reel_info"]:
                    try:
                        current_posts = len(combined_data["reel_info"]["data"][config.TARGET_QUERIES["timeline"]]["edges"])
                    except:
                        current_posts = 0

                # Check if we got new posts
                if current_posts == posts_count:
                    no_new_posts_count += 1
                    if no_new_posts_count >= 8:
                        log_message(f"No new posts after 3 scrolls, stopping at {current_posts} posts", 
                                  level="INFO", icon="⏹️")
                        break
                else:
                    no_new_posts_count = 0
                    posts_count = current_posts
                    log_message(f"Progress: {posts_count}/{config.MAX_POSTS} posts", level="INFO", icon="📊")

                # Stop if we've reached the target
                if posts_count >= config.MAX_POSTS:
                    log_message(f"Target reached: {posts_count} posts collected", level="SUCCESS", icon="✅")
                    break

                # Enhanced scrolling
                driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
                time.sleep(random.uniform(2.0, 3.0))
                
                # Additional scroll for stubborn pages
                if scroll_attempts % 5 == 0:
                    driver.execute_script("window.scrollBy(0, -200);")
                    time.sleep(0.5)
                    driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
                
                scroll_attempts += 1

            except Exception as scroll_error:
                log_message(f"Scroll error: {str(scroll_error)}", level="WARNING")
                break

        # Process and enhance location data
        if combined_data["reel_info"]:
            try:
                edges = combined_data["reel_info"]["data"][config.TARGET_QUERIES["timeline"]]["edges"]
                for edge in edges:
                    node = edge.get("node", {})
                    location = extract_location_data(node)
                    if location:
                        node["processed_location"] = location
            except Exception as e:
                log_message(f"Error processing locations: {str(e)}", level="WARNING")

        return combined_data

    except Exception as e:
        log_message(f"Error scraping profile: {str(e)}", level="ERROR")
        return {"profile_info": None, "reel_info": None}

def save_data(username, data, url, no_response_links, stats, done_urls, config):
    """Save the scraped data to a JSON file and handle failures."""
    if is_private_profile(data["profile_info"]) or not (data["profile_info"] or data["reel_info"]):
        with stats_lock:
            no_response_links.append(url)
            stats["failed"] += 1
        log_message(f"Private profile/no data: {username}", level="WARNING", icon="🔒")
        return False

    user_dir = os.path.join(config.OUTPUT_DIR, username)
    os.makedirs(user_dir, exist_ok=True)

    success = False
    
    # Save profile info
    if data["profile_info"]:
        with open(f"{user_dir}/userInfo.json", "w") as f:
            json.dump(data["profile_info"], f, indent=4)
        with stats_lock:
            stats["saved"] += 1
        log_message(f"Saved profile: {username}", level="SUCCESS", icon="💾")
        success = True

        if download_profile_picture(username, data["profile_info"], user_dir):
            with stats_lock:
                stats["pictures_downloaded"] += 1

    # Save post info with location data
    if data["reel_info"]:
        with open(f"{user_dir}/postInfo.json", "w") as f:
            json.dump(data["reel_info"], f, indent=4)
        
        # Count posts and locations
        try:
            edges = data["reel_info"]["data"][config.TARGET_QUERIES["timeline"]]["edges"]
            post_count = len(edges)
            location_count = sum(1 for edge in edges if edge.get("node", {}).get("processed_location"))
            
            with stats_lock:
                stats["posts_saved"] += post_count
                stats["locations_found"] += location_count
            
            log_message(f"Saved {post_count} posts ({location_count} with locations)", 
                       level="SUCCESS", icon="📝")
        except:
            pass

    # Dynamic wait time
    wait_time = random.uniform(1.5, 2.5)
    time.sleep(wait_time)

    if success:
        with done_urls_lock:
            done_urls.append(url)
            save_url_to_done_file(url, config)

    return success

def save_url_to_done_file(url, config):
    """Save a single URL to the done file and remove it from the input file."""
    try:
        if not os.path.exists(config.DONE_FILE):
            with open(config.DONE_FILE, 'w') as f:
                f.write("url\n")

        with open(config.DONE_FILE, 'a') as f:
            f.write(f"{url}\n")

        remove_url_from_input_file(url, config)
        return True
    except Exception as e:
        log_message(f"Error managing URL files: {str(e)}", level="ERROR")
        return False

def remove_url_from_input_file(url, config):
    """Remove a URL from the input file."""
    try:
        try:
            import pandas as pd
            input_df = pd.read_csv(config.INPUT_FILE)
            input_df = input_df[input_df['url'] != url]
            input_df.to_csv(config.INPUT_FILE, index=False)
        except Exception:
            # Fallback: rewrite CSV manually
            rows = []
            with open(config.INPUT_FILE, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for r in reader:
                    if r.get('url') and r.get('url').strip() != url.strip():
                        rows.append(r)
            # write back
            if rows:
                with open(config.INPUT_FILE, 'w', newline='', encoding='utf-8') as f:
                    w = csv.DictWriter(f, fieldnames=rows[0].keys())
                    w.writeheader()
                    w.writerows(rows)
            else:
                # clear file if no rows left
                open(config.INPUT_FILE, 'w').close()
        return True
    except Exception as e:
        log_message(f"Error removing URL from input file: {str(e)}", level="ERROR")
        return False

def download_profile_picture(username, profile_info, save_dir):
    """Download the highest quality profile picture available with retries."""
    try:
        pic_url = None
        quality_suffix = ""
        
        # Try to get the highest quality profile picture URL
        try:
            user_data = profile_info["data"]["user"]
            
            # Priority order: HD > high quality > standard
            if user_data.get("profile_pic_url_hd"):
                pic_url = user_data["profile_pic_url_hd"]

                log_message(f"Using HD profile picture for {username}", level="INFO", icon="🎨")
            elif user_data.get("hd_profile_pic_url_info", {}).get("url"):
                pic_url = user_data["hd_profile_pic_url_info"]["url"]

                log_message(f"Using HD profile picture (alt) for {username}", level="INFO", icon="🎨")
            elif user_data.get("profile_pic_url"):
                pic_url = user_data["profile_pic_url"]
                log_message(f"Using standard profile picture for {username}", level="WARNING", icon="⚠️")
            
            # Try to upgrade URL to highest quality by removing size restrictions
            if pic_url:
                # Remove size parameters to get original quality
                # Instagram URLs often have /sXXX/ pattern for size restrictions
                import re
                pic_url = re.sub(r'/s\d+x\d+/', '/s2048x2048/', pic_url)  # Request max size
                pic_url = re.sub(r'/vp/[^/]+/[^/]+/', '/vp/original/', pic_url, count=1)
                
        except (KeyError, TypeError) as e:
            log_message(f"Error accessing profile picture URL: {str(e)}", level="ERROR")
            return False

        if not pic_url:
            log_message(f"No profile picture URL found for {username}", level="WARNING")
            return False

        # Download with retries
        for attempt in range(3):
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Referer': 'https://www.instagram.com/'
                }
                
                response = requests.get(pic_url, stream=True, timeout=15, headers=headers)
                
                if response.status_code == 200:
                    # Determine file extension from content-type or URL
                    content_type = response.headers.get('content-type', '').lower()
                    if 'jpeg' in content_type or 'jpg' in content_type or '.jpg' in pic_url.lower():
                        ext = "jpg"
                    elif 'png' in content_type or '.png' in content_type or '.png' in pic_url.lower():
                        ext = "png"
                    elif 'webp' in content_type or '.webp' in content_type or '.webp' in pic_url.lower():
                        ext = "webp"
                    else:
                        ext = "jpg"  # Default to jpg
                    
                    file_path = os.path.join(save_dir, f"{username}{quality_suffix}.{ext}")

                    # Download with larger chunks for better performance
                    with open(file_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    # Verify file size
                    file_size = os.path.getsize(file_path)
                    file_size_kb = file_size / 1024
                    
                    if file_size > 0:
                        log_message(f"Downloaded profile picture: {username} ({file_size_kb:.2f} KB, {ext})", 
                                  level="SUCCESS", icon="🖼️")
                        return True
                    else:
                        log_message(f"Downloaded file is empty for {username}", level="WARNING")
                        os.remove(file_path)
                        
                elif response.status_code == 404:
                    log_message(f"Profile picture not found (404) for {username}", level="WARNING")
                    return False
                else:
                    log_message(f"Failed to download (HTTP {response.status_code}) for {username}", level="WARNING")
                    
            except requests.exceptions.Timeout:
                if attempt == 2:
                    log_message(f"Timeout downloading profile picture for {username} after 3 attempts", level="WARNING")
            except requests.exceptions.RequestException as e:
                if attempt == 2:
                    log_message(f"Failed to download profile picture for {username} after 3 attempts: {str(e)}", level="WARNING")
            except Exception as e:
                if attempt == 2:
                    log_message(f"Unexpected error downloading profile picture for {username}: {str(e)}", level="ERROR")
            
            # Wait before retry with exponential backoff
            if attempt < 2:
                time.sleep(1.5 ** (attempt + 1))

        return False
        
    except Exception as e:
        log_message(f"Critical error in download_profile_picture for {username}: {str(e)}", level="ERROR")
        return False


def worker_thread(url_queue, config, stats, no_response_links, progress_bar, done_urls):
    """Worker thread that processes URLs from a queue with rotating session IDs."""
    driver = None
    session_id = get_next_session_id(config)
    
    try:
        driver = configure_driver(session_id, config)
        if not driver:
            log_message("Failed to create browser instance for worker", level="ERROR")
            return

        while not url_queue.empty():
            try:
                url = url_queue.get(block=False)
            except queue.Empty:
                break

            try:
                username = get_username(url)
                sid_snip = (session_id[-10:] if session_id else 'no-sid')
                log_message(f"Processing: {username} (Session: ...{sid_snip})", level="INFO", icon="⚙️")

                data = scrape_profile(driver, url, config)
                save_data(username, data, url, no_response_links, stats, done_urls, config)

                progress_bar.update(1)

            except Exception as e:
                log_message(f"Failed to process {url}: {str(e)}", level="ERROR")
                with stats_lock:
                    no_response_links.append(url)
                    stats["failed"] += 1
                progress_bar.update(1)

            finally:
                url_queue.task_done()
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def _validate_sessions(config, max_check=2):
    """Quick HTTP preflight to check whether sessionids appear valid.
    Returns True if at least one session appears authenticated.
    """
    try:
        import requests
        from urllib.parse import unquote
    except Exception:
        return True
    checked = 0
    for s in (config.SESSION_IDS or []):
        if checked >= max_check:
            break
        checked += 1
        try:
            sid = unquote(s) if s else None
            sess = requests.Session()
            if sid:
                sess.cookies.set('sessionid', sid, domain='.instagram.com')
            r = sess.get('https://www.instagram.com/?__a=1&__d=dis', timeout=8)
            if r.status_code == 200:
                txt = (r.text or '').lower()[:200]
                if 'graphql' in txt or 'profile' in txt or r.headers.get('content-type','').lower().startswith('application/json'):
                    return True
        except Exception:
            continue
    return False

def load_urls(config):
    """Load URLs from input file, skipping those already in done file."""
    input_urls = []
    done_urls = []

    try:
        try:
            import pandas as pd
            df = pd.read_csv(config.INPUT_FILE)
            input_urls = df["url"].tolist()
        except Exception:
            # fallback to csv reader
            input_urls = []
            with open(config.INPUT_FILE, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for r in reader:
                    input_urls.append(r.get('url') or '')
        log_message(f"Loaded {len(input_urls)} URLs from {config.INPUT_FILE}", level="INFO", icon="📥")
    except Exception as e:
        log_message(f"Error reading input file: {str(e)}", level="ERROR")
        return [], []

    if os.path.exists(config.DONE_FILE):
        try:
            df_done = pd.read_csv(config.DONE_FILE)
            done_urls = df_done["url"].tolist()
            done_urls = [url.strip().rstrip('/') for url in done_urls]
            log_message(f"Loaded {len(done_urls)} completed URLs from {config.DONE_FILE}", 
                       level="INFO", icon="✅")
        except Exception as e:
            log_message(f"Error reading done file: {str(e)}", level="WARNING")

    normalized_input = [url.strip().rstrip('/') for url in input_urls]
    normalized_done = set(done_urls)

    urls_to_process = []
    for i, url in enumerate(input_urls):
        norm_url = normalized_input[i]
        if norm_url not in normalized_done:
            urls_to_process.append(url)

    skipped_count = len(input_urls) - len(urls_to_process)
    log_message(f"{skipped_count} URLs already processed, {len(urls_to_process)} remaining", 
               level="INFO", icon="📊")

    return urls_to_process, done_urls

def main(config):
    """Main function to orchestrate the scraping process."""
    log_message("="*70, level="INFO")
    log_message("Instagram Multi-Session Scraper @ale0", level="INFO", icon="🚀")
    log_message("="*70, level="INFO")
    log_message(f"Sessions: {len(config.SESSION_IDS)} | Workers: {config.MAX_WORKERS} | Max Posts: {config.MAX_POSTS}", 
               level="INFO", icon="⚙️")
    
    if config.TEST_MODE:
        log_message(f"TEST MODE: Processing only {config.MAX_TEST_PROFILES} profiles", 
                   level="WARNING", icon="🧪")

    # Quick preflight to check session validity (skip when test mode)
    if not config.TEST_MODE:
        ok = _validate_sessions(config)
        if not ok:
            log_message("Warning: session preflight failed — sessionids may be invalid or expired.", level="WARNING", icon="⚠️")

    start_time = time.time()

    stats = {
        "total": 0,
        "saved": 0,
        "failed": 0,
        "pictures_downloaded": 0,
        "posts_saved": 0,
        "locations_found": 0
    }

    urls_to_process, done_urls = load_urls(config)

    if config.TEST_MODE and len(urls_to_process) > config.MAX_TEST_PROFILES:
        urls_to_process = urls_to_process[:config.MAX_TEST_PROFILES]

    no_response_links = []
    stats["total"] = len(urls_to_process)

    if len(urls_to_process) == 0:
        log_message("No new URLs to process.", level="INFO", icon="✅")
        return

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    url_queue = queue.Queue()
    for url in urls_to_process:
        url_queue.put(url)

    threads = []
    newly_completed_urls = []

    log_message(f"Starting {config.MAX_WORKERS} parallel workers...", level="INFO", icon="🔧")

    with tqdm(total=len(urls_to_process), desc="Processing Profiles", 
              bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]') as progress_bar:
        for i in range(config.MAX_WORKERS):
            thread = threading.Thread(
                target=worker_thread,
                args=(url_queue, config, stats, no_response_links, progress_bar, newly_completed_urls),
                name=f"Worker-{i+1}"
            )
            thread.daemon = True
            thread.start()
            threads.append(thread)
            time.sleep(0.5)  # Stagger worker starts

        url_queue.join()

    # Wait for all threads to complete
    for thread in threads:
        thread.join(timeout=30)

    if no_response_links:
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)
        noresp_path = os.path.join(config.OUTPUT_DIR, "noResponse.csv")
        try:
            try:
                import pandas as pd
                pd.DataFrame({"url": no_response_links}).to_csv(noresp_path, index=False)
            except Exception:
                with open(noresp_path, 'w', newline='', encoding='utf-8') as f:
                    w = csv.writer(f)
                    w.writerow(['url'])
                    for u in no_response_links:
                        w.writerow([u])
            log_message(f"Failed URLs saved to {noresp_path}", level="WARNING", icon="⚠️")
        except Exception as e:
            log_message(f"Failed to save failed URLs: {e}", level="ERROR")

    # Final statistics
    elapsed_time = time.time() - start_time
    log_message("\n" + "="*70, level="SUCCESS")
    log_message("SCRAPING COMPLETE", level="SUCCESS", icon="🎉")
    log_message("="*70, level="SUCCESS")
    log_message(f"Total URLs processed: {stats['total']}", level="INFO", icon="📊")
    log_message(f"Successfully saved profiles: {stats['saved']}", level="SUCCESS", icon="✅")
    log_message(f"Profile pictures downloaded: {stats['pictures_downloaded']}", level="INFO", icon="🖼️")
    log_message(f"Total posts saved: {stats['posts_saved']}", level="INFO", icon="📝")
    log_message(f"Posts with locations: {stats['locations_found']}", level="INFO", icon="📍")
    log_message(f"Failed/Private profiles: {stats['failed']}", level="WARNING", icon="⚠️")
    log_message(f"Completed in {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)", 
               level="INFO", icon="⏱️")
    log_message(f"Average time per profile: {elapsed_time/max(stats['total'], 1):.2f} seconds", 
               level="INFO", icon="📈")
    log_message("="*70, level="SUCCESS")


if __name__ == '__main__':
    # Load config from .env (if available) and construct ScraperConfig
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    from urllib.parse import unquote
    env_sids = os.getenv("IG_SESSION_IDS", "")
    if env_sids:
        sids = [s.strip() for s in env_sids.split(",") if s.strip()]
        # decode percent-encoded values
        try:
            sids = [unquote(s) for s in sids]
        except Exception:
            pass
    else:
        sids = []

    cfg = ScraperConfig(
        SESSION_IDS=sids or [None],
        MAX_WORKERS=int(os.getenv("DEFAULT_WORKERS", "8")),
        MAX_POSTS=int(os.getenv("DEFAULT_MAX_POSTS", "40")),
        HEADLESS=os.getenv("DEFAULT_HEADLESS", "true").lower() in ("1", "true", "yes"),
        INPUT_FILE=os.getenv("DEFAULT_INPUT", "data/input.csv"),
        DONE_FILE=os.getenv("DEFAULT_DONE", "data/inputdone.csv"),
        TEST_MODE=os.getenv("DEFAULT_TEST", "false").lower() in ("1", "true", "yes"),
        MAX_TEST_PROFILES=int(os.getenv("DEFAULT_TEST_PROFILES", "5")),
        OUTPUT_DIR=os.getenv("DEFAULT_OUTPUT_DIR", "data/output"),
    )
    main(cfg)
