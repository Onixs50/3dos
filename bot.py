import requests
import time
from datetime import datetime
from colorama import init, Fore, Style
from threading import Thread
import concurrent.futures
import os
import random

init(autoreset=True)
BASE_URL = "https://api.dashboard.3dos.io"
PROXY_SOURCES = [
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/all.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt"
]

def load_tokens():
    try:
        with open("token.txt", "r") as file:
            tokens = [line.strip() for line in file if line.strip()]
            if not tokens:
                raise ValueError("No tokens found in token.txt")
            return tokens
    except FileNotFoundError:
        print(Fore.RED + "[ERROR] File 'token.txt' not found. Please create a file named 'token.txt' and add your tokens.")
        exit(1)
    except Exception as e:
        print(Fore.RED + f"[ERROR] Failed to load tokens: {e}")
        exit(1)

def load_proxies_from_file():
    try:
        with open("proxy.txt", "r") as file:
            proxies = [line.strip() for line in file if line.strip()]
            if proxies:
                print(Fore.GREEN + f"[INFO] Loaded {len(proxies)} proxies from proxy.txt")
            else:
                print(Fore.YELLOW + "[WARNING] No proxies found in proxy.txt. Using direct connection.")
            return proxies
    except FileNotFoundError:
        print(Fore.YELLOW + "[WARNING] File 'proxy.txt' not found. Using direct connection without proxies.")
        return []
    except Exception as e:
        print(Fore.RED + f"[ERROR] Failed to load proxies: {e}")
        return []

def fetch_online_proxies():
    all_proxies = []
    
    for url in PROXY_SOURCES:
        try:
            print(Fore.CYAN + f"[{datetime.now()}] Fetching proxies from {url}...")
            response = requests.get(url, timeout=15)
            if response.status_code == 200:
                proxies = [line.strip() for line in response.text.splitlines() if line.strip()]
                print(Fore.GREEN + f"[INFO] Successfully fetched {len(proxies)} proxies from {url}")
                all_proxies.extend(proxies)
            else:
                print(Fore.RED + f"[ERROR] Failed to fetch proxies from {url}. Status code: {response.status_code}")
        except Exception as e:
            print(Fore.RED + f"[ERROR] Failed to fetch online proxies from {url}: {e}")
    
    # Remove duplicates
    all_proxies = list(set(all_proxies))
    print(Fore.GREEN + f"[INFO] Total unique proxies fetched: {len(all_proxies)}")
    return all_proxies

def format_proxy(proxy):
    """Format proxy string to ensure it has the correct protocol prefix"""
    if proxy.startswith('http://') or proxy.startswith('https://') or \
       proxy.startswith('socks4://') or proxy.startswith('socks5://'):
        return proxy
    
    # Default to http if no protocol specified
    return f"http://{proxy}"

def test_proxy(proxy):
    try:
        # Format proxy correctly based on its type
        formatted_proxy = proxy
        if not (proxy.startswith('http://') or proxy.startswith('https://') or 
                proxy.startswith('socks4://') or proxy.startswith('socks5://')):
            # If no protocol is specified, try to guess based on common patterns
            if 'socks4' in proxy.lower():
                formatted_proxy = f"socks4://{proxy.split('socks4://')[-1]}"
            elif 'socks5' in proxy.lower():
                formatted_proxy = f"socks5://{proxy.split('socks5://')[-1]}"
            else:
                formatted_proxy = f"http://{proxy}"
        
        proxies = {
            "http": formatted_proxy,
            "https": formatted_proxy
        }
        
        # Use a timeout to avoid hanging on slow proxies
        response = requests.get("https://httpbin.org/ip", proxies=proxies, timeout=8)
        if response.status_code == 200:
            print(Fore.GREEN + f"[{datetime.now()}] Working proxy found: {formatted_proxy}")
            return formatted_proxy
    except Exception as e:
        # Silently fail for non-working proxies
        pass
    
    return None

def get_working_proxies(proxies, max_workers=50, max_proxies=100):
    working_proxies = []
    total = len(proxies)
    
    # Shuffle the proxies to avoid testing them in the same order every time
    random.shuffle(proxies)
    
    # Limit the number of proxies to test to avoid excessive runtime
    test_proxies = proxies[:1000] if len(proxies) > 1000 else proxies
    
    print(Fore.CYAN + f"[{datetime.now()}] Testing {len(test_proxies)} proxies for connectivity...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_proxy = {executor.submit(test_proxy, proxy): proxy for proxy in test_proxies}
        completed = 0
        
        for future in concurrent.futures.as_completed(future_to_proxy):
            completed += 1
            
            if completed % 50 == 0 or completed == len(test_proxies):
                print(Fore.YELLOW + f"[{datetime.now()}] Testing progress: {completed}/{len(test_proxies)} proxies")
            
            result = future.result()
            if result:
                working_proxies.append(result)
                # If we've found enough working proxies, we can stop testing
                if len(working_proxies) >= max_proxies:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
    
    print(Fore.GREEN + f"[{datetime.now()}] Found {len(working_proxies)} working proxies out of {len(test_proxies)} tested")
    
    # Save working proxies to file for future use
    if working_proxies:
        try:
            with open("working_proxies.txt", "w") as f:
                for proxy in working_proxies:
                    f.write(f"{proxy}\n")
            print(Fore.GREEN + f"[{datetime.now()}] Saved {len(working_proxies)} working proxies to working_proxies.txt")
        except Exception as e:
            print(Fore.RED + f"[ERROR] Failed to save working proxies: {e}")
    
    return working_proxies

def make_post_request(endpoint, headers, data=None, proxy=None):
    url = f"{BASE_URL}{endpoint}"
    try:
        proxies = {"http": proxy, "https": proxy} if proxy else None
        response = requests.post(url, headers=headers, json=data, proxies=proxies, timeout=15)
        return response
    except requests.exceptions.RequestException as e:
        print(f"{Fore.RED}[{datetime.now()}] Request failed with proxy {proxy}: {e}")
        return None

def get_new_working_proxy(available_proxies, token_id, failed_proxies):
    """Find a new working proxy for a token"""
    # Filter out failed proxies
    potential_proxies = [p for p in available_proxies if p not in failed_proxies]
    
    if not potential_proxies:
        print(f"{Fore.YELLOW}[{datetime.now()}] No more available proxies for token {token_id}. Resetting failed proxies list.")
        # Reset failed proxies if we've exhausted all options
        failed_proxies.clear()
        potential_proxies = available_proxies
    
    # Try proxies until we find one that works
    for proxy in potential_proxies:
        try:
            print(f"{Fore.CYAN}[{datetime.now()}] Testing new proxy {proxy} for token {token_id}...")
            proxies = {"http": proxy, "https": proxy}
            response = requests.get("https://httpbin.org/ip", proxies=proxies, timeout=8)
            if response.status_code == 200:
                print(f"{Fore.GREEN}[{datetime.now()}] Found new working proxy {proxy} for token {token_id}")
                return proxy
        except:
            failed_proxies.add(proxy)
    
    # If no proxy works, return None to use direct connection
    print(f"{Fore.YELLOW}[{datetime.now()}] No working proxy found for token {token_id}. Using direct connection.")
    return None

def process_token(token, available_proxies):
    token_id = token[:10]  # Use first 10 chars as token ID for logging
    
    headers_general = {
        "accept": "application/json, text/plain, */*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9",
        "authorization": f"Bearer {token}",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": "https://dashboard.3dos.io",
        "pragma": "no-cache",
        "referer": "https://dashboard.3dos.io/register?ref_code=1c744d",
        "sec-ch-ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    }

    # Keep track of failed proxies for this token
    failed_proxies = set()
    
    # Initially no proxy is assigned
    current_proxy = None
    
    # If we have proxies available, try to get a working one
    if available_proxies:
        current_proxy = get_new_working_proxy(available_proxies, token_id, failed_proxies)

    print(f"{Fore.CYAN}[{datetime.now()}] Token {token_id} starting with proxy: {current_proxy if current_proxy else 'Direct Connection'}")

    while True:
        try:
            # Try with current proxy
            profile_response = make_post_request("/api/profile/me", headers_general, {}, current_proxy)
            
            # If the request failed with the current proxy, get a new one
            if not profile_response or profile_response.status_code != 200:
                print(f"{Fore.RED}[{datetime.now()}] Request failed for token {token_id} with proxy {current_proxy}")
                
                if current_proxy:
                    # Add current proxy to failed list
                    failed_proxies.add(current_proxy)
                    # Get a new working proxy
                    current_proxy = get_new_working_proxy(available_proxies, token_id, failed_proxies)
                    print(f"{Fore.YELLOW}[{datetime.now()}] Switching to new proxy: {current_proxy if current_proxy else 'Direct Connection'} for token {token_id}")
                
                time.sleep(5)
                continue
            
            # Process successful response
            profile_data = profile_response.json()
            status = profile_data.get("status")
            email = profile_data.get("data", {}).get("email")
            loyalty_points = profile_data.get("data", {}).get("loyalty_points")

            print(f"{Fore.GREEN}[PROFILE DATA for token {token_id}...]")
            print(f"{Fore.CYAN}Status: {status}")
            print(f"{Fore.CYAN}Email: {email}")
            print(f"{Fore.CYAN}Loyalty Points: {loyalty_points}")
            print(f"{Fore.CYAN}Using proxy: {current_proxy if current_proxy else 'Direct Connection'}")

            api_secret = profile_data.get("data", {}).get("api_secret")
            if api_secret:
                print(f"{Fore.GREEN}[{datetime.now()}] API Secret Found: {api_secret}")
                profile_api_endpoint = f"/api/profile/api/{api_secret}"
                profile_api_response = make_post_request(profile_api_endpoint, headers_general, {}, current_proxy)
                if profile_api_response and profile_api_response.status_code == 200:
                    profile_api_data = profile_api_response.json().get("data", {})
                    print(f"{Fore.GREEN}[PROFILE API DATA for token {token_id}...]")
                    print(f"{Fore.CYAN}Username: {profile_api_data.get('username')}")
                    print(f"{Fore.CYAN}Tier: {profile_api_data.get('tier', {}).get('tier_name')}")
                    print(f"{Fore.CYAN}Next Tier: {profile_api_data.get('next_tier', {}).get('tier_name')}")
                    print(f"{Fore.CYAN}Daily Reward Claim: {profile_api_data.get('daily_reward_claim')}")
                else:
                    print(f"{Fore.RED}[{datetime.now()}] Profile API request failed for token {token_id}...")
                    # If the API request fails, we don't necessarily need to change the proxy
                    # since the main profile request worked
            else:
                print(f"{Fore.RED}[{datetime.now()}] API Secret not found for token {token_id}...")

            # Wait before the next cycle - this token keeps using the same proxy until it fails
            time.sleep(10)

        except Exception as e:
            print(f"{Fore.RED}[{datetime.now()}] An error occurred for token {token_id}: {e}")
            
            # If an exception occurred, the proxy might be bad
            if current_proxy:
                failed_proxies.add(current_proxy)
                current_proxy = get_new_working_proxy(available_proxies, token_id, failed_proxies)
                print(f"{Fore.YELLOW}[{datetime.now()}] Error occurred, switching to new proxy: {current_proxy if current_proxy else 'Direct Connection'} for token {token_id}")
            
            time.sleep(10)

def load_working_proxies_from_file():
    try:
        if os.path.exists("working_proxies.txt"):
            with open("working_proxies.txt", "r") as file:
                proxies = [line.strip() for line in file if line.strip()]
                if proxies:
                    print(Fore.GREEN + f"[INFO] Loaded {len(proxies)} previously working proxies")
                    return proxies
    except Exception as e:
        print(Fore.RED + f"[ERROR] Failed to load working proxies: {e}")
    
    return []

def display_menu():
    os.system('cls' if os.name == 'nt' else 'clear')
    print(Fore.CYAN + "=" * 60)
    print(Fore.CYAN + "3DOS DASHBOARD API CLIENT".center(60))
    print(Fore.CYAN + "=" * 60)
    print(Fore.YELLOW + "[1] Use proxies from local proxy.txt file")
    print(Fore.YELLOW + "[2] Fetch and test proxies automatically from online sources")
    print(Fore.YELLOW + "[3] Use previously tested working proxies (from working_proxies.txt)")
    print(Fore.YELLOW + "[4] Run without proxies (direct connection)")
    print(Fore.YELLOW + "[5] Exit")
    print(Fore.CYAN + "=" * 60)

def main():
    while True:
        display_menu()
        choice = input(Fore.GREEN + "Enter your choice (1-5): ")
        
        if choice == '1':
            proxies = load_proxies_from_file()
            if proxies:
                break
            else:
                print(Fore.RED + "No proxies found in proxy.txt. Press Enter to return to menu...")
                input()
                continue
        elif choice == '2':
            online_proxies = fetch_online_proxies()
            if online_proxies:
                proxies = get_working_proxies(online_proxies)
                if proxies:
                    print(Fore.GREEN + f"Using {len(proxies)} verified working proxies")
                    break
                else:
                    print(Fore.RED + "No working proxies found. Press Enter to return to menu...")
                    input()
                    continue
            else:
                print(Fore.RED + "Failed to fetch online proxies. Press Enter to return to menu...")
                input()
                continue
        elif choice == '3':
            proxies = load_working_proxies_from_file()
            if proxies:
                print(Fore.GREEN + f"Using {len(proxies)} previously verified working proxies")
                break
            else:
                print(Fore.RED + "No previously working proxies found. Press Enter to return to menu...")
                input()
                continue
        elif choice == '4':
            proxies = []
            print(Fore.YELLOW + "Running without proxies (direct connection)")
            break
        elif choice == '5':
            print(Fore.CYAN + "Exiting program...")
            exit(0)
        else:
            print(Fore.RED + "Invalid choice. Press Enter to continue...")
            input()
    
    tokens = load_tokens()
    threads = []

    print(Fore.GREEN + f"Starting processes for {len(tokens)} tokens...")
    
    for token in tokens:
        thread = Thread(target=process_token, args=(token, proxies))
        thread.daemon = True
        thread.start()
        threads.append(thread)
        time.sleep(1)  # Small delay between starting threads

    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\nKeyboard interrupt detected. Exiting gracefully...")
        exit(0)

if __name__ == "__main__":
    main()