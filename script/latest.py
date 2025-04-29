import time
import os
import sys
import signal
import shutil
import atexit
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementNotInteractableException,
    ElementClickInterceptedException,
    StaleElementReferenceException
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import threading

# Configurable parameters
LOGIN_URL = "https://www.epassport.gov.bd/authorization/login"
TARGET_DATE = datetime.now().strftime("%d/%m/%y")  # Today's date by default
REFRESH_INTERVAL = 0.5  # Seconds between refresh attempts
MAX_RETRIES = 50  # Maximum number of retries before switching delivery type
SOUND_ALERT = True  # Play sound alerts
HEADLESS = False  # Run in headless mode for faster execution
DEBUG_SCREENSHOTS = True  # Take screenshots during critical operations
CONSIDER_ANY_DATE = True  # If True, will try to book ANY available date

# Initialize chrome options
chrome_options = Options()
chrome_options.binary_location = (
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
)

# Performance optimizations
chrome_options.add_argument("--disable-extensions")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-infobars")
chrome_options.add_argument("--disable-notifications")
chrome_options.add_argument("--disable-popup-blocking")

if HEADLESS:
    chrome_options.add_argument("--headless")

# Allow faster page loading
chrome_options.page_load_strategy = 'eager'

# Driver setup
service = Service("/opt/homebrew/bin/chromedriver")
driver = None  # Will be initialized in main_task

# Setup logging
import random
run_id = random.randint(1000, 9999)
run_folder = f"run_{run_id}"
os.makedirs(run_folder, exist_ok=True)
LOG_FILE = os.path.join(run_folder, f"log-{run_id}.txt")

def log_message(message):
    """Log a message to both console and file"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    formatted_message = f"[{timestamp}] {message}"
    print(formatted_message)
    
    try:
        with open(LOG_FILE, "a") as log_file:
            log_file.write(f"{formatted_message}\n")
    except Exception as e:
        print(f"Error writing to log: {e}")

def cleanup_resources():
    """Clean up resources before exiting"""
    log_message("🧹 Performing cleanup...")
    
    # Close the browser if it's still open
    global driver
    if driver:
        try:
            driver.quit()
            log_message("🛑 Browser closed successfully.")
        except Exception as e:
            log_message(f"⚠️ Error closing browser: {e}")
    
    # Delete temporary Chrome files if needed
    try:
        chrome_temp = os.path.expanduser("~/Library/Caches/BraveSoftware")
        if os.path.exists(chrome_temp):
            log_message(f"🧹 Cleaning browser cache...")
            # Instead of removing, we could just clear specific files
    except Exception as e:
        log_message(f"⚠️ Error cleaning browser cache: {e}")
    
    log_message("✅ Cleanup completed")

# Register cleanup function to run on exit
atexit.register(cleanup_resources)

# Handle signals for cleaner termination
def signal_handler(sig, frame):
    log_message("📢 Received termination signal. Cleaning up...")
    cleanup_resources()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def play_sound(sound_file="/System/Library/Sounds/Funk.aiff", repeat=1):
    """Play a sound notification"""
    if SOUND_ALERT:
        for _ in range(repeat):
            os.system(f"afplay {sound_file}")

def wait_for_element(locator, timeout=10, condition=EC.presence_of_element_located):
    """Wait for an element with improved error handling"""
    try:
        return WebDriverWait(driver, timeout).until(condition(locator))
    except TimeoutException:
        log_message(f"⏳ Timeout waiting for element: {locator}")
        return None
    except Exception as e:
        log_message(f"❌ Error waiting for element: {locator}, {e}")
        return None

def safe_click(locator, timeout=5, scroll=True, retry=1):
    """Safely click an element with retries and improved error handling"""
    for attempt in range(retry + 1):
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable(locator)
            )
            if scroll:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});", 
                    element
                )
                time.sleep(0.1)  # Small pause after scrolling
            
            element.click()
            return True
        except StaleElementReferenceException:
            if attempt < retry:
                log_message(f"⚠️ Stale element, retrying click: {locator}")
                time.sleep(0.2)
                continue
            log_message(f"❌ Element became stale: {locator}")
            return False
        except Exception as e:
            if attempt < retry:
                log_message(f"⚠️ Click failed, retrying: {locator}")
                time.sleep(0.2)
                continue
            log_message(f"❌ Error clicking element: {locator}, {e}")
            return False
    return False

def alternate_delivery_button(selected_delivery):
    """Switch between delivery options with improved speed"""
    delivery_types = {
        "Regular delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.REGULAR']",
        "Express delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.EXPRESS']",
    }
    next_delivery = (
        "Express delivery"
        if selected_delivery == "Regular delivery"
        else "Regular delivery"
    )
    
    if safe_click((By.XPATH, delivery_types[next_delivery]), retry=2):
        log_message(f"✅ Switched to '{next_delivery}'")
        time.sleep(0.5)  # Reduced wait time after switching
        return next_delivery
    else:
        log_message(f"⚠️ Failed to switch to '{next_delivery}'.")
        return selected_delivery

def check_for_errors():
    """Check for error messages on the page with minimal wait time"""
    error_message_container = driver.find_elements(By.CLASS_NAME, "error-messages")
    if error_message_container and error_message_container[0].is_displayed():
        error_text = error_message_container[0].text.strip()
        log_message(f"❌ Error detected: {error_text}")
        return True
    return False

def handle_failure_and_retry():
    """Handle failures more efficiently"""
    log_message("🔄 Refreshing page...")
    play_sound()
    
    try:
        # Take screenshot before refresh for debugging
        take_debug_screenshot("before_refresh")
        
        # Try to stop any ongoing page loading
        driver.execute_script("window.stop();")
        
        # Clear cookies to prevent potential session issues
        driver.delete_all_cookies()
        
        # Execute refresh
        driver.refresh()
        
        # Wait for page to at least begin loading
        WebDriverWait(driver, 5).until(
            lambda d: d.execute_script("return document.readyState") != "complete"
        )
        
        # Wait for page to finish loading
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        
        log_message("✅ Page refreshed successfully")
        take_debug_screenshot("after_refresh")
    except Exception as e:
        log_message(f"⚠️ Error during refresh: {e}")
        # Try alternative refresh method
        try:
            driver.get(driver.current_url)
            log_message("✅ Used alternative refresh method")
        except Exception:
            log_message("❌ All refresh methods failed")
    
    # Wait shorter time after refresh
    time.sleep(1)

def periodic_refresher(stop_event, interval=60):
    """Keep the session alive by doing background actions"""
    while not stop_event.is_set():
        time.sleep(interval)
        try:
            if driver and driver.current_url and "epassport.gov.bd" in driver.current_url:
                log_message("🔄 Keeping session alive...")
                # Execute minimal JavaScript to keep session active
                driver.execute_script("return document.readyState;")
        except Exception:
            pass  # Ignore errors in background thread

def take_debug_screenshot(name):
    """Take a debug screenshot if enabled"""
    if DEBUG_SCREENSHOTS:
        try:
            filename = f"{run_folder}/debug_{name}_{int(time.time())}.png"
            driver.save_screenshot(filename)
            log_message(f"📷 Debug screenshot: {filename}")
        except Exception as e:
            log_message(f"⚠️ Failed to take debug screenshot: {e}")

def find_any_available_date():
    """Find any available date on the calendar"""
    log_message("🔍 Looking for ANY available date...")
    
    try:
        # Find all available (non-disabled) dates
        available_dates = driver.find_elements(
            By.XPATH, 
            "//div[contains(@class, 'btn-light') and not(contains(@class, 'disabled')) and not(contains(@class, 'outside'))]"
        )
        
        if available_dates:
            log_message(f"✅ Found {len(available_dates)} available dates!")
            return available_dates[0]  # Return the first available date
        else:
            log_message("❌ No available dates found.")
            return None
    except Exception as e:
        log_message(f"❌ Error finding available dates: {e}")
        return None

def main_task():
    """Main task with improved performance and reliability"""
    global driver
    
    # Initialize log file
    with open(LOG_FILE, "w") as log_file:
        log_file.write("=== ePassport Booking Automation Log ===\n")
    
    log_message(f"🚀 Starting automation run #{run_id}")
    log_message(f"📅 Target date: {TARGET_DATE}")
    log_message(f"⚙️ CONSIDER_ANY_DATE: {CONSIDER_ANY_DATE}")
    
    try:
        # Initialize driver
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30)
        
        # Start background session keeper
        stop_refresher = threading.Event()
        refresher_thread = threading.Thread(
            target=periodic_refresher, 
            args=(stop_refresher,), 
            daemon=True
        )
        refresher_thread.start()
        
        # Navigate to login page
        driver.get(LOGIN_URL)
        log_message("🌐 Opened the login page")
        
        user_input = input("Complete login and press ENTER when ready to proceed: ")
        log_message("👤 User indicated login complete")
        
        # Wait for calendar to load
        calendar = wait_for_element((By.CLASS_NAME, "ngb-dp-content"), timeout=90)
        if not calendar:
            log_message("❌ Calendar failed to load. Exiting.")
            return
            
        log_message("📅 Calendar loaded successfully.")
        take_debug_screenshot("calendar_loaded")
        
        # Parse target date
        target_date = datetime.strptime(TARGET_DATE, "%d/%m/%y")
        target_day = target_date.day
        
        selected_delivery = "Regular delivery"
        retry_count = 0
        
        # Main booking loop
        while True:
            date_clicked = False
            
            try:
                # More robust date selection strategy
                log_message(f"🔍 Looking for available date {target_day}...")
                
                # First wait for the calendar to be fully loaded
                wait_for_element((By.CLASS_NAME, "ngb-dp-month"), timeout=5)
                
                # Get only the selectable dates (not disabled, not outside current month)
                date_xpath = f"//div[contains(@class, 'btn-light') and not(contains(@class, 'disabled')) and not(contains(@class, 'outside')) and normalize-space(text())='{target_day}']"
                
                # Try JavaScript-based approach first
                try:
                    # Find all calendar days
                    all_days = driver.find_elements(By.XPATH, "//div[contains(@class, 'ngb-dp-day')]//div[not(contains(@class, 'disabled'))]")
                    log_message(f"📅 Found {len(all_days)} available dates in calendar")
                    
                    # Find days that match our target day
                    matching_days = []
                    for day in all_days:
                        if day.text.strip() == str(target_day) and "outside" not in day.get_attribute("class"):
                            matching_days.append(day)
                    
                    if matching_days:
                        log_message(f"🎯 Found {len(matching_days)} matching dates for day {target_day}")
                        date_element = matching_days[0]  # Pick the first matching date
                    else:
                        date_element = None
                        log_message(f"⚠️ No matching dates found for day {target_day}")
                except Exception as e:
                    log_message(f"⚠️ Error finding dates with JS approach: {e}")
                    date_element = None
                
                # If JavaScript method failed, try conventional approach
                if not date_element:
                    try:
                        date_elements = driver.find_elements(By.XPATH, date_xpath)
                        if date_elements:
                            date_element = date_elements[0]
                    except Exception:
                        date_element = None
                
                if date_element:
                    # Scroll to the element first
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});", 
                        date_element
                    )
                    time.sleep(0.3)  # Small pause to ensure element is viewable
                    
                    # Try JavaScript click first (more reliable)
                    try:
                        driver.execute_script("arguments[0].click();", date_element)
                        log_message(f"✅ Clicked date {target_day} using JavaScript")
                    except Exception:
                        # If JS click fails, try regular click
                        date_element.click()
                        log_message(f"✅ Clicked date {target_day} using regular click")
                    
                    if check_for_errors():
                        retry_count += 1
                        if retry_count >= MAX_RETRIES:
                            selected_delivery = alternate_delivery_button(selected_delivery)
                            retry_count = 0
                        continue
                    
                    log_message(f"✅ Date {target_day} selected under '{selected_delivery}'.")
                    date_clicked = True
                else:
                    log_message("⚠️ Target date not available. Switching delivery option...")
                    selected_delivery = alternate_delivery_button(selected_delivery)
                    retry_count = 0
                    continue
                    
            except Exception as e:
                log_message(f"❌ Error during date selection: {e}")
                handle_failure_and_retry()
                continue
            
            # Fast time slot selection
            try:
                log_message("⏳ Waiting for time slots...")
                take_debug_screenshot("waiting_for_timeslots")
                
                # Try to find time slots with multiple strategies
                time_slots_container = None
                
                # Strategy 1: Direct class lookup
                time_slots_container = wait_for_element(
                    (By.CLASS_NAME, "vbeop-time-slots"), 
                    timeout=5
                )
                
                # Strategy 2: Find by containing text
                if not time_slots_container:
                    try:
                        time_container_xpath = "//div[contains(text(), 'time slot')]/ancestor::div[contains(@class, 'section')]"
                        time_slots_container = wait_for_element(
                            (By.XPATH, time_container_xpath),
                            timeout=5
                        )
                    except Exception:
                        pass
                
                # Strategy 3: Look for any time slot directly
                if not time_slots_container:
                    try:
                        time_slot = wait_for_element(
                            (By.CLASS_NAME, "time-slot"),
                            timeout=3
                        )
                        if time_slot:
                            time_slots_container = time_slot.find_element(By.XPATH, "./..")
                    except Exception:
                        pass
                
                if not time_slots_container:
                    log_message("⚠️ Time slots container not found. Retrying...")
                    handle_failure_and_retry()
                    continue
                
                take_debug_screenshot("found_timeslots")
                
                # Get all available time slots with several methods
                available_slots = []
                
                # Method 1: Using time-slot class
                try:
                    time_slot_labels = driver.find_elements(By.CLASS_NAME, "time-slot")
                    log_message(f"📊 Found {len(time_slot_labels)} total time slot labels")
                    
                    for time_slot in time_slot_labels:
                        try:
                            slot_id = time_slot.get_attribute("for")
                            if not slot_id:
                                continue
                                
                            associated_input = driver.find_element(By.ID, slot_id)
                            
                            if associated_input.is_enabled() and not associated_input.get_attribute("disabled"):
                                available_slots.append((time_slot, time_slot.text))
                        except Exception as e:
                            continue
                except Exception as e:
                    log_message(f"⚠️ Error finding slots by class: {e}")
                
                # Method 2: Using XPath as backup
                if not available_slots:
                    try:
                        slot_xpath = "//label[contains(@class, 'time-slot') and not(contains(@class, 'disabled'))]"
                        slot_elements = driver.find_elements(By.XPATH, slot_xpath)
                        
                        for slot in slot_elements:
                            try:
                                available_slots.append((slot, slot.text))
                            except Exception:
                                continue
                    except Exception as e:
                        log_message(f"⚠️ Error finding slots by XPath: {e}")
                
                log_message(f"📊 Found {len(available_slots)} available time slots")
                
                if not available_slots:
                    take_debug_screenshot("no_available_slots")
                    log_message("❌ No available time slots. Switching delivery option...")
                    selected_delivery = alternate_delivery_button(selected_delivery)
                    retry_count = 0
                    continue
                
                # Select the first available slot
                slot, slot_text = available_slots[0]
                log_message(f"⏰ Selecting time slot: {slot_text}")
                
                # Try multiple clicking strategies
                click_success = False
                
                # Strategy 1: JavaScript click
                try:
                    driver.execute_script("arguments[0].click();", slot)
                    time.sleep(0.3)
                    click_success = True
                    log_message("✅ Selected time slot using JavaScript click")
                except Exception as e:
                    log_message(f"⚠️ JS click failed: {e}")
                
                # Strategy 2: Regular click
                if not click_success:
                    try:
                        slot.click()
                        time.sleep(0.3)
                        click_success = True
                        log_message("✅ Selected time slot using regular click")
                    except Exception as e:
                        log_message(f"⚠️ Regular click failed: {e}")
                
                # Strategy 3: Action chains
                if not click_success:
                    try:
                        from selenium.webdriver.common.action_chains import ActionChains
                        actions = ActionChains(driver)
                        actions.move_to_element(slot).click().perform()
                        time.sleep(0.3)
                        click_success = True
                        log_message("✅ Selected time slot using action chains")
                    except Exception as e:
                        log_message(f"❌ All click methods failed: {e}")
                        handle_failure_and_retry()
                        continue
                
                if check_for_errors():
                    log_message("❌ Error after selecting time slot. Retrying...")
                    handle_failure_and_retry()
                    continue
                    
                log_message(f"✅ Slot selected successfully: {slot_text}")
                take_debug_screenshot("slot_selected")
                
                # Find the save button with multiple strategies
                save_button = None
                
                # Strategy 1: Direct XPath
                save_button = wait_for_element(
                    (By.XPATH, "//span[text()='Save and continue']/.."),
                    timeout=3
                )
                
                # Strategy 2: Button contains text
                if not save_button:
                    save_button = wait_for_element(
                        (By.XPATH, "//button[contains(., 'Save')]"),
                        timeout=2
                    )
                
                # Strategy 3: Any button at bottom
                if not save_button:
                    try:
                        buttons = driver.find_elements(By.TAG_NAME, "button")
                        for button in buttons:
                            if "save" in button.text.lower() or "continue" in button.text.lower():
                                save_button = button
                                break
                    except Exception:
                        pass
                
                if not save_button:
                    log_message("❌ Save button not found. Retrying...")
                    handle_failure_and_retry()
                    continue
                
                # Try multiple click strategies on save button
                click_success = False
                
                # Strategy 1: JavaScript click
                try:
                    driver.execute_script("arguments[0].click();", save_button)
                    click_success = True
                    log_message("✅ Clicked 'Save and Continue' button using JavaScript")
                except Exception:
                    pass
                
                # Strategy 2: Regular click
                if not click_success:
                    try:
                        save_button.click()
                        click_success = True
                        log_message("✅ Clicked 'Save and Continue' button using regular click")
                    except Exception:
                        pass
                
                if not click_success:
                    log_message("❌ Failed to click save button. Retrying...")
                    handle_failure_and_retry()
                    continue
                
                log_message("✅ Clicked 'Save and Continue' button.")
                
                # Wait for summary page to load
                success = wait_for_element(
                    (By.XPATH, "//div[contains(@class, 'summary-section')]"),
                    timeout=15
                )
                
                if success and "/summary" in driver.current_url:
                    log_message("🎉 SUCCESS! Summary page loaded!")
                    log_message(f"🔗 URL: {driver.current_url}")
                    
                    # Take screenshot for verification
                    screenshot_path = f"{run_folder}/schedule-{run_id}.png"
                    driver.save_screenshot(screenshot_path)
                    log_message(f"📷 Screenshot saved to {screenshot_path}")
                    
                    # Play success sound notification
                    play_sound("/System/Library/Sounds/Glass.aiff", repeat=3)
                    
                    # Stop the background refresher
                    stop_refresher.set()
                    
                    # Wait for user confirmation before closing
                    input("🎯 Booking successful! Press ENTER to close the browser...")
                    return
                else:
                    log_message("❌ Failed to reach summary page. Retrying...")
                    handle_failure_and_retry()
                    continue
                    
            except Exception as e:
                log_message(f"❌ Error during booking process: {e}")
                handle_failure_and_retry()
                continue
            
    except Exception as e:
        log_message(f"❌ Critical error: {e}")
        play_sound("/System/Library/Sounds/Sosumi.aiff", repeat=2)
    finally:
        # Ensure resources are cleaned up
        if 'stop_refresher' in locals() and stop_refresher:
            stop_refresher.set()
        
        cleanup_resources()

if __name__ == "__main__":
    try:
        main_task()
    except KeyboardInterrupt:
        log_message("👋 Script terminated by user")
    except Exception as e:
        log_message(f"💥 Unexpected error: {e}")
    finally:
        # Final cleanup to ensure no resources are left
        cleanup_resources()
        
        # Clear terminal if on macOS/Linux
        if sys.platform != "win32":
            os.system('clear')