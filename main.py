import logging
import subprocess
import sys
import threading
import time
from datetime import datetime
from threading import Event
import random
import requests
import os
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Setup basic logging first
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

def log_message(message, level="info"):
    """Log messages with different levels"""
    if level == "info":
        logger.info(message)
    elif level == "error":
        logger.error(message)
    elif level == "warning":
        logger.warning(message)
    else:
        logger.info(message)

# Load configuration
try:
    from config import *
except ImportError:
    log_message("config.py not found. Please copy config_template.py to config.py and configure it.", level="error")
    sys.exit(1)

def extract_info(driver):
    """Extract booking information from summary page using proven method"""
    try:
        # Extract Name and Appointment Time using exact XPaths
        name_xpath = "//tr[td[text()='Full name (as per NID/BRC)']]/td[2]"
        time_xpath = "//tr[td[text()='Appointment time']]/td[2]"
        
        # Wait for summary page to load completely
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, name_xpath))
        )
        
        name = driver.find_element(By.XPATH, name_xpath).text.strip()
        raw_time = driver.find_element(By.XPATH, time_xpath).text.strip()
        
        # Format date and time as per original logic
        date_part = " ".join(raw_time.split(",")[0].split()[:2])  # Format date
        time_part = raw_time.split(",")[1].strip()  # Extract time
        appointment_time = f"{date_part}, {time_part}"

        # Navigate to Account Edit Page and Get Email
        driver.get("https://www.epassport.gov.bd/home/account/edit")
        time.sleep(2)
        email_xpath = "//input[@type='email']"
        try:
            email_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, email_xpath))
            )
            email = email_element.get_attribute("value").strip()
        except TimeoutException:
            log_message("Email input field not found after waiting", level="error")
            email = "Email not found"

        return name, appointment_time, email
        
    except Exception as e:
        log_message(f"Info extraction failed: {e}", level="error")
        return "Unknown", "Unknown", "Unknown"

def send_telegram_message(name, time_str, email):
    """Send booking confirmation via Telegram using proven method"""
    message = f"Name: {name}\nTime: {time_str}\nEmail: {email}"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    for chat_id in TELEGRAM_CHAT_IDS:
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        try:
            response = requests.post(url, data=payload)
            if response.status_code == 200:
                log_message(f"Telegram sent to {chat_id}")
                return True
            else:
                log_message(f"Telegram failed to {chat_id}", level="error")
        except Exception as e:
            log_message(f"Telegram error: {e}", level="error")
    
    return False

CONFIG = {
    "BRAVE_PATH": BRAVE_PATH,
    "CHROMEDRIVER_PATH": CHROMEDRIVER_PATH,
    "TARGET_DATE_STR": datetime.now().strftime("%d/%m/%y"),
    "DELIVERY_TYPES": {
        "Regular delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.REGULAR']",
        "Express delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.EXPRESS']",
    },
    "SOUND_PATHS": {
        "refresh": REFRESH_SOUND_PATH,
        "success": SUCCESS_SOUND_PATH,
    },
    "HOT_WINDOW": {
        "START_SEC": HOT_WINDOW_START,
        "END_SEC": HOT_WINDOW_END,
        "RAPID_SWITCH_INTERVAL": SWITCH_INTERVAL,
        "UI_DELAY_COMPENSATION": 1.0,
    }
}

def create_optimized_driver():
    """Create optimized Chrome driver for faster performance"""
    chrome_options = Options()
    
    # Check if browser path exists
    if not Path(CONFIG["BRAVE_PATH"]).exists():
        log_message(f"Browser not found at: {CONFIG['BRAVE_PATH']}", level="error")
        log_message("Please update BRAVE_PATH in config.py", level="error")
        raise FileNotFoundError("Browser not found")
    
    chrome_options.binary_location = CONFIG["BRAVE_PATH"]
    
    # Performance optimizations
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-images")
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
    try:
        # Check if chromedriver exists
        if not Path(CONFIG["CHROMEDRIVER_PATH"]).exists():
            log_message(f"ChromeDriver not found at: {CONFIG['CHROMEDRIVER_PATH']}", level="error")
            log_message("Please update CHROMEDRIVER_PATH in config.py", level="error")
            raise FileNotFoundError("ChromeDriver not found")
            
        return webdriver.Chrome(
            service=Service(CONFIG["CHROMEDRIVER_PATH"]), options=chrome_options
        )
    except Exception as e:
        log_message(f"Driver creation failed: {e}", level="error")
        raise

def is_in_hot_window():
    """Check if current time is in the critical slot opening window"""
    now = datetime.now()
    seconds = now.second
    return seconds >= CONFIG["HOT_WINDOW"]["START_SEC"] or seconds <= CONFIG["HOT_WINDOW"]["END_SEC"]

def get_hot_window_remaining_time():
    """Get remaining time in current hot window"""
    now = datetime.now()
    seconds = now.second
    
    if seconds >= CONFIG["HOT_WINDOW"]["START_SEC"]:
        return (60 - seconds) + CONFIG["HOT_WINDOW"]["END_SEC"]
    elif seconds <= CONFIG["HOT_WINDOW"]["END_SEC"]:
        return CONFIG["HOT_WINDOW"]["END_SEC"] - seconds
    else:
        return 0

def fast_click_delivery_option(driver, delivery_type):
    """Ultra-fast delivery option switching using JavaScript"""
    try:
        xpath = CONFIG["DELIVERY_TYPES"][delivery_type]
        element = driver.find_element(By.XPATH, xpath)
        driver.execute_script("arguments[0].click();", element)
        return True
    except Exception:
        return False

def quick_error_check(driver):
    """Quick check for error message box"""
    try:
        errors = driver.find_elements(By.CLASS_NAME, "error-messages")
        return len(errors) > 0
    except:
        return False

def check_no_slots_message(driver):
    """Check for 'No time slots available' message"""
    try:
        no_slots_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'No time slots available')]")
        return len(no_slots_elements) > 0
    except:
        return False

def wait_for_next_hot_window():
    """Wait until next hot window with countdown"""
    while not session_terminated_event.is_set():
        now = datetime.now()
        seconds = now.second
        
        if is_in_hot_window():
            return
        
        if seconds < CONFIG["HOT_WINDOW"]["START_SEC"]:
            wait_time = CONFIG["HOT_WINDOW"]["START_SEC"] - seconds
        else:
            wait_time = (60 - seconds) + CONFIG["HOT_WINDOW"]["START_SEC"]
        
        if wait_time > 10:
            log_message(f"Next hot window in {wait_time}s")
        
        time.sleep(min(wait_time - 1, 10))

def hot_window_rapid_switching(driver, target_day, driver_id):
    """Memory-efficient rapid switching during hot window"""
    log_message(f"D{driver_id}: HOT WINDOW")
    
    delivery_options = ["Regular delivery", "Express delivery"]
    current_option = driver_id % 2
    
    start_time = time.time()
    remaining_time = get_hot_window_remaining_time()
    
    switch_count = 0
    
    # Cache XPath selectors for faster access
    delivery_xpaths = [CONFIG["DELIVERY_TYPES"][opt] for opt in delivery_options]
    date_xpath = f"//div[@class='btn-light' and text()='{target_day}']"
    
    while (time.time() - start_time) < remaining_time and not session_terminated_event.is_set():
        current_delivery = delivery_options[current_option]
        
        # Fast switch using cached xpath
        try:
            element = driver.find_element(By.XPATH, delivery_xpaths[current_option])
            driver.execute_script("arguments[0].click();", element)
            switch_count += 1
            
            if switch_count % 60 == 0:
                log_message(f"D{driver_id}: {switch_count} switches")
                if quick_error_check(driver):
                    log_message(f"D{driver_id}: Error box detected")
                    return False, None, None
            
            # Optimized date checking
            for check_delay in [0, 0.3, 0.8]:
                if session_terminated_event.is_set():
                    return False, None, None
                    
                if check_delay > 0:
                    time.sleep(check_delay)
                
                try:
                    date_element = driver.find_element(By.XPATH, date_xpath)
                    if "disabled" not in date_element.get_attribute("class"):
                        if quick_error_check(driver):
                            log_message(f"D{driver_id}: Error before date click")
                            return False, None, None
                            
                        log_message(f"D{driver_id}: SLOT FOUND - {current_delivery}")
                        
                        driver.execute_script("arguments[0].click();", date_element)
                        current_time = datetime.now().strftime("%H%M%S")
                        try:
                            driver.save_screenshot(f"{current_time}.png")
                        except Exception:
                            pass
                        return True, current_delivery, date_element
                except NoSuchElementException:
                    pass
                
                if check_delay >= 0.8:
                    break
        except Exception:
            pass
        
        current_option = 1 - current_option
        time.sleep(CONFIG["HOT_WINDOW"]["RAPID_SWITCH_INTERVAL"])
    
    log_message(f"D{driver_id}: Window ended - {switch_count} switches")
    return False, None, None

def handle_slot_selection_fast(driver, driver_id):
    """Optimized slot selection with minimal delays"""
    try:
        log_message(f"D{driver_id}: Loading slots")
        time_slots_container = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "vbeop-time-slots"))
        )
        
        if check_no_slots_message(driver):
            log_message(f"D{driver_id}: No slots - ending session")
            session_terminated_event.set()
            return False
        
        time_slot_labels = time_slots_container.find_elements(By.CLASS_NAME, "time-slot")
        
        if not time_slot_labels:
            log_message(f"D{driver_id}: No slot elements")
            session_terminated_event.set()
            return False
        
        random.shuffle(time_slot_labels)
        
        for time_slot in time_slot_labels:
            try:
                associated_input = driver.find_element(By.ID, time_slot.get_attribute("for"))
                if associated_input.is_enabled():
                    log_message(f"D{driver_id}: Selecting slot")
                    driver.execute_script("arguments[0].click();", time_slot)
                    log_message(f"D{driver_id}: Slot selected")
                    return True
            except Exception:
                continue
        
        log_message(f"D{driver_id}: No enabled slots")
        session_terminated_event.set()
        return False
        
    except Exception as e:
        log_message(f"D{driver_id}: Slot selection failed: {e}", level="error")
        session_terminated_event.set()
        return False

def automate_booking_optimized(driver, initial_delivery, drivers, driver_id):
    """Optimized booking automation focused on hot windows only"""
    target_date = datetime.strptime(CONFIG["TARGET_DATE_STR"], "%d/%m/%y")
    target_day = target_date.day

    try:
        WebDriverWait(driver, 90).until(
            EC.presence_of_element_located((By.CLASS_NAME, "ngb-dp-content"))
        )
        log_message(f"D{driver_id}: Calendar loaded")
    except TimeoutException:
        log_message(f"D{driver_id}: Calendar timeout", level="error")
        session_terminated_event.set()
        return

    if not fast_click_delivery_option(driver, initial_delivery):
        log_message(f"D{driver_id}: Initial delivery click failed", level="error")
        session_terminated_event.set()
        return
    
    while not session_terminated_event.is_set():
        wait_for_next_hot_window()
        
        if session_terminated_event.is_set():
            break
            
        success, found_delivery, date_element = hot_window_rapid_switching(driver, target_day, driver_id)
        
        if success:
            if handle_slot_selection_fast(driver, driver_id):
                try:
                    save_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//span[text()='Save and continue']"))
                    )
                    driver.execute_script("arguments[0].click();", save_button)
                    log_message(f"D{driver_id}: Save clicked")
                    
                    # Check for errors after save and continue - CONTINUE instead of terminating
                    time.sleep(1)
                    if quick_error_check(driver):
                        log_message(f"D{driver_id}: Slot taken - trying next window")
                        continue  # Continue to next hot window instead of terminating
                    
                    # Play success sound if file exists
                    try:
                        if Path(CONFIG["SOUND_PATHS"]["success"]).exists():
                            subprocess.run(["afplay", CONFIG["SOUND_PATHS"]["success"]], check=False)
                    except:
                        pass
                    
                    try:
                        WebDriverWait(driver, 30).until(
                            EC.url_matches(r"https://www.epassport.gov.bd/applications/application-form/.*/summary")
                        )
                        log_message(f"D{driver_id}: SUCCESS - Summary loaded")
                        
                        # Send Telegram notification using proven method
                        try:
                            name, appointment_time, email = extract_info(driver)
                            telegram_success = send_telegram_message(name, appointment_time, email)
                            if telegram_success:
                                log_message(f"D{driver_id}: Telegram sent - DONE")
                            else:
                                log_message(f"D{driver_id}: Telegram failed but booking successful")
                            session_terminated_event.set()
                            return
                        except Exception as e:
                            log_message(f"D{driver_id}: Extraction error: {e}", level="error")
                            # Send basic success message even if extraction fails
                            try:
                                basic_message = f"Passport slot booked at {datetime.now().strftime('%H:%M:%S')}. Check browser for details."
                                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                                for chat_id in TELEGRAM_CHAT_IDS:
                                    payload = {"chat_id": chat_id, "text": basic_message}
                                    requests.post(url, data=payload, timeout=5)
                                log_message(f"D{driver_id}: Basic telegram sent - DONE")
                            except:
                                log_message(f"D{driver_id}: All telegram failed but booking successful")
                            session_terminated_event.set()
                            return
                    except TimeoutException:
                        log_message(f"D{driver_id}: Summary timeout", level="error")
                        session_terminated_event.set()
                        return
                    
                except Exception as e:
                    log_message(f"D{driver_id}: Save failed: {e}", level="error")
                    continue  # Continue to next hot window instead of terminating
        else:
            log_message(f"D{driver_id}: No date found")
        
        time.sleep(1)

# Event flags
session_terminated_event = Event()

def run_automate_booking_optimized(driver, delivery, drivers, driver_id):
    try:
        if not session_terminated_event.is_set():
            automate_booking_optimized(driver, delivery, drivers, driver_id)
    except Exception as e:
        session_terminated_event.set()
        log_message(f"D{driver_id} thread error: {e}", level="error")
    finally:
        log_message(f"D{driver_id} thread done")

def cleanup_drivers(drivers):
    for i, driver in enumerate(drivers):
        try:
            log_message(f"Closing D{i+1}")
            driver.quit()
        except Exception as e:
            log_message(f"D{i+1} close error: {e}", level="warning")

def main():
    drivers = []
    try:
        log_message("Creating drivers...")
        driver1 = create_optimized_driver()
        driver2 = create_optimized_driver()
        drivers.extend([driver1, driver2])
        log_message("Drivers created")
    except Exception:
        log_message("Driver creation failed", level="error")
        cleanup_drivers(drivers)
        return

    try:
        driver1.get("https://www.epassport.gov.bd/authorization/login")
        driver2.get("https://www.epassport.gov.bd/authorization/login")
        log_message("Login pages opened")

        input("Press ENTER after login...")

        thread1 = threading.Thread(
            target=run_automate_booking_optimized, 
            args=(driver1, "Regular delivery", drivers, 1)
        )
        thread2 = threading.Thread(
            target=run_automate_booking_optimized, 
            args=(driver2, "Express delivery", drivers, 2)
        )

        log_message("Starting automation...")
        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()

        log_message("All threads completed")

    except KeyboardInterrupt:
        log_message("Interrupted by user")
        session_terminated_event.set()
    except Exception as e:
        log_message(f"Main error: {e}", level="error")
    finally:
        cleanup_drivers(drivers)
        log_message("Exit")

if __name__ == "__main__":
    main()