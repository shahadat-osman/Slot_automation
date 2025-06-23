import logging
import subprocess
import sys
import threading
import time
from datetime import datetime
from threading import Event
import random
import requests
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

def log_message(message, level="info"):
    """Log messages with different levels"""
    getattr(logger, level, logger.info)(message)

# Load configuration
try:
    from config import *
except ImportError:
    log_message("config.py not found. Please copy config_template.py to config.py and configure it.", level="error")
    sys.exit(1)

# Configuration constants
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
    },
    "TIMEOUTS": {
        "CALENDAR_LOAD": 90,
        "SLOT_LOAD": 10,
        "SAVE_BUTTON": 5,
        "SUMMARY_PAGE": 30,
        "EMAIL_FIELD": 10,
    }
}

# XPath constants
XPATHS = {
    "NAME": "//tr[td[text()='Full name (as per NID/BRC)']]/td[2]",
    "TIME": "//tr[td[text()='Appointment time']]/td[2]",
    "EMAIL": "//input[@type='email']",
    "SAVE_BUTTON": "//span[text()='Save and continue']",
    "NO_SLOTS": "//*[contains(text(), 'No time slots available')]",
    "ERROR_MESSAGES": "error-messages",
    "TIME_SLOTS_CONTAINER": "vbeop-time-slots",
    "TIME_SLOT": "time-slot",
    "CALENDAR": "ngb-dp-content",
}

# Global event flag
session_terminated_event = Event()

class PassportAutomation:
    """Main automation class for passport slot booking"""
    
    def __init__(self, driver_id, delivery_type):
        self.driver_id = driver_id
        self.delivery_type = delivery_type
        self.driver = None
        self.target_day = datetime.strptime(CONFIG["TARGET_DATE_STR"], "%d/%m/%y").day
        
    def create_driver(self):
        """Create optimized Chrome driver"""
        chrome_options = Options()
        
        # Validate paths
        if not Path(CONFIG["BRAVE_PATH"]).exists():
            raise FileNotFoundError(f"Browser not found at: {CONFIG['BRAVE_PATH']}")
        
        if not Path(CONFIG["CHROMEDRIVER_PATH"]).exists():
            raise FileNotFoundError(f"ChromeDriver not found at: {CONFIG['CHROMEDRIVER_PATH']}")
        
        chrome_options.binary_location = CONFIG["BRAVE_PATH"]
        
        # Performance optimizations
        performance_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage", 
            "--disable-extensions",
            "--disable-plugins",
            "--disable-images",
            "--disable-blink-features=AutomationControlled"
        ]
        
        for arg in performance_args:
            chrome_options.add_argument(arg)
            
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        
        try:
            self.driver = webdriver.Chrome(
                service=Service(CONFIG["CHROMEDRIVER_PATH"]), 
                options=chrome_options
            )
            log_message(f"D{self.driver_id}: Driver created")
            return self.driver
        except Exception as e:
            log_message(f"D{self.driver_id}: Driver creation failed: {e}", level="error")
            raise

    def extract_booking_info(self):
        """Extract booking information from summary page"""
        try:
            # Wait for summary page
            WebDriverWait(self.driver, CONFIG["TIMEOUTS"]["SUMMARY_PAGE"]).until(
                EC.presence_of_element_located((By.XPATH, XPATHS["NAME"]))
            )
            
            # Extract name and time
            name = self.driver.find_element(By.XPATH, XPATHS["NAME"]).text.strip()
            raw_time = self.driver.find_element(By.XPATH, XPATHS["TIME"]).text.strip()
            
            # Format time
            date_part = " ".join(raw_time.split(",")[0].split()[:2])
            time_part = raw_time.split(",")[1].strip()
            appointment_time = f"{date_part}, {time_part}"

            # Get email from account page
            email = self._extract_email()
            
            return name, appointment_time, email
            
        except Exception as e:
            log_message(f"D{self.driver_id}: Info extraction failed: {e}", level="error")
            return "Unknown", "Unknown", "Unknown"

    def _extract_email(self):
        """Extract email from account edit page"""
        try:
            self.driver.get("https://www.epassport.gov.bd/home/account/edit")
            time.sleep(2)
            
            email_element = WebDriverWait(self.driver, CONFIG["TIMEOUTS"]["EMAIL_FIELD"]).until(
                EC.presence_of_element_located((By.XPATH, XPATHS["EMAIL"]))
            )
            return email_element.get_attribute("value").strip()
            
        except TimeoutException:
            log_message(f"D{self.driver_id}: Email field not found", level="warning")
            return "Email not found"

    def send_telegram_notification(self, name, time_str, email):
        """Send booking confirmation via Telegram"""
        message = f"Name: {name}\nTime: {time_str}\nEmail: {email}"
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        
        for chat_id in TELEGRAM_CHAT_IDS:
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
            }
            try:
                response = requests.post(url, data=payload, timeout=10)
                if response.status_code == 200:
                    log_message(f"D{self.driver_id}: Telegram sent to {chat_id}")
                    return True
                else:
                    log_message(f"D{self.driver_id}: Telegram failed to {chat_id}", level="error")
            except Exception as e:
                log_message(f"D{self.driver_id}: Telegram error: {e}", level="error")
        
        return False

    def send_fallback_notification(self):
        """Send basic notification if extraction fails"""
        try:
            basic_message = f"Passport slot booked at {datetime.now().strftime('%H:%M:%S')}. Check browser for details."
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            
            for chat_id in TELEGRAM_CHAT_IDS:
                payload = {"chat_id": chat_id, "text": basic_message}
                requests.post(url, data=payload, timeout=5)
            
            log_message(f"D{self.driver_id}: Fallback telegram sent")
            return True
        except Exception:
            log_message(f"D{self.driver_id}: All telegram failed", level="error")
            return False

    def is_in_hot_window(self):
        """Check if current time is in the critical slot opening window"""
        seconds = datetime.now().second
        return (seconds >= CONFIG["HOT_WINDOW"]["START_SEC"] or 
                seconds <= CONFIG["HOT_WINDOW"]["END_SEC"])

    def get_hot_window_remaining_time(self):
        """Get remaining time in current hot window"""
        seconds = datetime.now().second
        
        if seconds >= CONFIG["HOT_WINDOW"]["START_SEC"]:
            return (60 - seconds) + CONFIG["HOT_WINDOW"]["END_SEC"]
        elif seconds <= CONFIG["HOT_WINDOW"]["END_SEC"]:
            return CONFIG["HOT_WINDOW"]["END_SEC"] - seconds
        else:
            return 0

    def wait_for_hot_window(self):
        """Wait until next hot window"""
        while not session_terminated_event.is_set():
            if self.is_in_hot_window():
                return
            
            seconds = datetime.now().second
            if seconds < CONFIG["HOT_WINDOW"]["START_SEC"]:
                wait_time = CONFIG["HOT_WINDOW"]["START_SEC"] - seconds
            else:
                wait_time = (60 - seconds) + CONFIG["HOT_WINDOW"]["START_SEC"]
            
            if wait_time > 10:
                log_message(f"D{self.driver_id}: Next hot window in {wait_time}s")
            
            time.sleep(min(wait_time - 1, 10))

    def fast_click_delivery_option(self, delivery_type):
        """Fast delivery option switching using JavaScript"""
        try:
            xpath = CONFIG["DELIVERY_TYPES"][delivery_type]
            element = self.driver.find_element(By.XPATH, xpath)
            self.driver.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            return False

    def quick_error_check(self):
        """Quick check for error message box"""
        try:
            errors = self.driver.find_elements(By.CLASS_NAME, XPATHS["ERROR_MESSAGES"])
            return len(errors) > 0
        except Exception:
            return False

    def check_no_slots_message(self):
        """Check for 'No time slots available' message"""
        try:
            no_slots = self.driver.find_elements(By.XPATH, XPATHS["NO_SLOTS"])
            return len(no_slots) > 0
        except Exception:
            return False

    def rapid_switching_in_hot_window(self):
        """Perform rapid switching during hot window"""
        log_message(f"D{self.driver_id}: HOT WINDOW")
        
        delivery_options = ["Regular delivery", "Express delivery"]
        current_option = self.driver_id % 2
        
        start_time = time.time()
        remaining_time = self.get_hot_window_remaining_time()
        switch_count = 0
        
        # Cache XPaths for performance
        delivery_xpaths = [CONFIG["DELIVERY_TYPES"][opt] for opt in delivery_options]
        date_xpath = f"//div[@class='btn-light' and text()='{self.target_day}']"
        
        while ((time.time() - start_time) < remaining_time and 
               not session_terminated_event.is_set()):
            
            current_delivery = delivery_options[current_option]
            
            try:
                # Fast switch using cached xpath
                element = self.driver.find_element(By.XPATH, delivery_xpaths[current_option])
                self.driver.execute_script("arguments[0].click();", element)
                switch_count += 1
                
                # Log progress and check for errors periodically
                if switch_count % 60 == 0:
                    log_message(f"D{self.driver_id}: {switch_count} switches")
                    if self.quick_error_check():
                        log_message(f"D{self.driver_id}: Error box detected")
                        return False, None
                
                # Check for available date with UI delay compensation
                for check_delay in [0, 0.3, 0.8]:
                    if session_terminated_event.is_set():
                        return False, None
                        
                    if check_delay > 0:
                        time.sleep(check_delay)
                    
                    if self._check_and_click_date(date_xpath, current_delivery):
                        return True, current_delivery
                    
                    if check_delay >= 0.8:
                        break
                        
            except Exception:
                pass  # Continue switching on any error
            
            # Switch to other delivery option
            current_option = 1 - current_option
            time.sleep(CONFIG["HOT_WINDOW"]["RAPID_SWITCH_INTERVAL"])
        
        log_message(f"D{self.driver_id}: Window ended - {switch_count} switches")
        return False, None

    def _check_and_click_date(self, date_xpath, current_delivery):
        """Check if date is clickable and click it"""
        try:
            date_element = self.driver.find_element(By.XPATH, date_xpath)
            if "disabled" not in date_element.get_attribute("class"):
                if self.quick_error_check():
                    log_message(f"D{self.driver_id}: Error before date click")
                    return False
                    
                log_message(f"D{self.driver_id}: SLOT FOUND - {current_delivery}")
                
                self.driver.execute_script("arguments[0].click();", date_element)
                self._save_screenshot()
                return True
        except NoSuchElementException:
            pass
        
        return False

    def _save_screenshot(self):
        """Save screenshot with timestamp"""
        try:
            timestamp = datetime.now().strftime("%H%M%S")
            self.driver.save_screenshot(f"{timestamp}.png")
        except Exception:
            pass  # Ignore screenshot errors

    def handle_slot_selection(self):
        """Handle time slot selection"""
        try:
            log_message(f"D{self.driver_id}: Loading slots")
            
            # Wait for slots container
            time_slots_container = WebDriverWait(self.driver, CONFIG["TIMEOUTS"]["SLOT_LOAD"]).until(
                EC.presence_of_element_located((By.CLASS_NAME, XPATHS["TIME_SLOTS_CONTAINER"]))
            )
            
            # Check for no slots message
            if self.check_no_slots_message():
                log_message(f"D{self.driver_id}: No slots - ending session")
                session_terminated_event.set()
                return False
            
            # Get available slots
            time_slot_labels = time_slots_container.find_elements(By.CLASS_NAME, XPATHS["TIME_SLOT"])
            
            if not time_slot_labels:
                log_message(f"D{self.driver_id}: No slot elements")
                session_terminated_event.set()
                return False
            
            # Try to select an available slot
            random.shuffle(time_slot_labels)
            
            for time_slot in time_slot_labels:
                try:
                    associated_input = self.driver.find_element(By.ID, time_slot.get_attribute("for"))
                    if associated_input.is_enabled():
                        log_message(f"D{self.driver_id}: Selecting slot")
                        self.driver.execute_script("arguments[0].click();", time_slot)
                        log_message(f"D{self.driver_id}: Slot selected")
                        return True
                except Exception:
                    continue
            
            log_message(f"D{self.driver_id}: No enabled slots")
            session_terminated_event.set()
            return False
            
        except Exception as e:
            log_message(f"D{self.driver_id}: Slot selection failed: {e}", level="error")
            session_terminated_event.set()
            return False

    def process_booking_success(self):
        """Handle successful booking - save, notify, and cleanup"""
        try:
            # Click save and continue
            save_button = WebDriverWait(self.driver, CONFIG["TIMEOUTS"]["SAVE_BUTTON"]).until(
                EC.element_to_be_clickable((By.XPATH, XPATHS["SAVE_BUTTON"]))
            )
            self.driver.execute_script("arguments[0].click();", save_button)
            log_message(f"D{self.driver_id}: Save clicked")
            
            # Check for slot conflict errors
            time.sleep(1)
            if self.quick_error_check():
                log_message(f"D{self.driver_id}: Slot taken - trying next window")
                return False  # Continue to next hot window
            
            # Play success sound
            self._play_success_sound()
            
            # Wait for summary page
            WebDriverWait(self.driver, CONFIG["TIMEOUTS"]["SUMMARY_PAGE"]).until(
                EC.url_matches(r"https://www.epassport.gov.bd/applications/application-form/.*/summary")
            )
            log_message(f"D{self.driver_id}: SUCCESS - Summary loaded")
            
            # Send notifications
            self._send_success_notifications()
            
            session_terminated_event.set()
            return True
            
        except Exception as e:
            log_message(f"D{self.driver_id}: Save process failed: {e}", level="error")
            return False  # Continue to next hot window

    def _play_success_sound(self):
        """Play success sound if available"""
        try:
            if Path(CONFIG["SOUND_PATHS"]["success"]).exists():
                subprocess.run(["afplay", CONFIG["SOUND_PATHS"]["success"]], check=False)
        except Exception:
            pass

    def _send_success_notifications(self):
        """Send success notifications via Telegram"""
        try:
            name, appointment_time, email = self.extract_booking_info()
            
            if self.send_telegram_notification(name, appointment_time, email):
                log_message(f"D{self.driver_id}: Telegram sent - DONE")
            else:
                log_message(f"D{self.driver_id}: Telegram failed but booking successful")
                
        except Exception as e:
            log_message(f"D{self.driver_id}: Notification error: {e}", level="error")
            self.send_fallback_notification()

    def initialize_calendar(self):
        """Initialize and wait for calendar to load"""
        try:
            WebDriverWait(self.driver, CONFIG["TIMEOUTS"]["CALENDAR_LOAD"]).until(
                EC.presence_of_element_located((By.CLASS_NAME, XPATHS["CALENDAR"]))
            )
            log_message(f"D{self.driver_id}: Calendar loaded")
            
            if not self.fast_click_delivery_option(self.delivery_type):
                log_message(f"D{self.driver_id}: Initial delivery click failed", level="error")
                session_terminated_event.set()
                return False
                
            return True
            
        except TimeoutException:
            log_message(f"D{self.driver_id}: Calendar timeout", level="error")
            session_terminated_event.set()
            return False

    def run_automation(self):
        """Main automation loop"""
        try:
            # Initialize
            if not self.create_driver():
                return
                
            self.driver.get("https://www.epassport.gov.bd/authorization/login")
            log_message(f"D{self.driver_id}: Login page opened")
            
            # Wait for manual login (handled in main)
            
            if not self.initialize_calendar():
                return
            
            # Main booking loop
            while not session_terminated_event.is_set():
                self.wait_for_hot_window()
                
                if session_terminated_event.is_set():
                    break
                
                # Try to find and book a slot
                success, delivery = self.rapid_switching_in_hot_window()
                
                if success:
                    if self.handle_slot_selection():
                        if self.process_booking_success():
                            break  # Successful booking
                        # else: continue to next hot window
                else:
                    log_message(f"D{self.driver_id}: No date found")
                
                time.sleep(1)  # Brief pause before next attempt
                
        except Exception as e:
            log_message(f"D{self.driver_id}: Automation error: {e}", level="error")
            session_terminated_event.set()
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up driver resources"""
        try:
            if self.driver:
                log_message(f"D{self.driver_id}: Cleaning up")
                self.driver.quit()
        except Exception as e:
            log_message(f"D{self.driver_id}: Cleanup error: {e}", level="warning")

def run_automation_thread(driver_id, delivery_type):
    """Thread function to run automation"""
    try:
        automation = PassportAutomation(driver_id, delivery_type)
        automation.run_automation()
    except Exception as e:
        log_message(f"D{driver_id}: Thread error: {e}", level="error")
        session_terminated_event.set()
    finally:
        log_message(f"D{driver_id}: Thread completed")

def main():
    """Main function"""
    log_message("Starting passport slot booking automation")
    
    # Create automation threads
    threads = []
    automations = []
    
    try:
        # Create drivers and get to login page
        automation1 = PassportAutomation(1, "Regular delivery")
        automation2 = PassportAutomation(2, "Express delivery")
        automations = [automation1, automation2]
        
        # Create drivers
        automation1.create_driver()
        automation2.create_driver()
        
        # Navigate to login pages
        automation1.driver.get("https://www.epassport.gov.bd/authorization/login")
        automation2.driver.get("https://www.epassport.gov.bd/authorization/login")
        log_message("Login pages opened")

        # Wait for manual login
        input("Press ENTER after login...")

        # Initialize calendars
        if not automation1.initialize_calendar() or not automation2.initialize_calendar():
            log_message("Calendar initialization failed", level="error")
            return

        # Start automation threads
        thread1 = threading.Thread(target=run_automation_thread, args=(1, "Regular delivery"))
        thread2 = threading.Thread(target=run_automation_thread, args=(2, "Express delivery"))
        threads = [thread1, thread2]

        log_message("Starting automation threads...")
        thread1.start()
        thread2.start()

        # Wait for completion
        thread1.join()
        thread2.join()

        log_message("All threads completed")

    except KeyboardInterrupt:
        log_message("Interrupted by user")
        session_terminated_event.set()
    except Exception as e:
        log_message(f"Main error: {e}", level="error")
        session_terminated_event.set()
    finally:
        # Cleanup all resources
        for automation in automations:
            automation.cleanup()
        log_message("Cleanup completed - Exit")

if __name__ == "__main__":
    main()