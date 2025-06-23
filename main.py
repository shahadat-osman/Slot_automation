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

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

def log_message(message, level="info"):
    """Log messages with different levels"""
    getattr(logger, level, logger.info)(message)

try:
    from config import *
except ImportError:
    log_message("config.py not found. Please copy config_template.py to config.py and configure it.", level="error")
    sys.exit(1)

required_vars = ['BRAVE_PATH', 'CHROMEDRIVER_PATH', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_IDS', 'EMAILS', 'EMAIL_PASSWORD']
missing_vars = [var for var in required_vars if var not in globals()]
if missing_vars:
    log_message(f"Missing required config variables: {missing_vars}", level="error")
    sys.exit(1)

CONFIG = {
    "BRAVE_PATH": BRAVE_PATH,
    "CHROMEDRIVER_PATH": CHROMEDRIVER_PATH,
    # "TARGET_DATE_STR": "23/10/25"
    "TARGET_DATE_STR": datetime.now().strftime("%d/%m/%y"),
    "DELIVERY_TYPES": {
        "Regular delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.REGULAR']",
        "Express delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.EXPRESS']",
    },
    "SOUND_PATHS": {
        "refresh": getattr(sys.modules[__name__], 'REFRESH_SOUND_PATH', ''),
        "success": getattr(sys.modules[__name__], 'SUCCESS_SOUND_PATH', ''),
    },
    "HOT_WINDOW": {
        "START_SEC": getattr(sys.modules[__name__], 'HOT_WINDOW_START', 48),
        "END_SEC": getattr(sys.modules[__name__], 'HOT_WINDOW_END', 15),
        "RAPID_SWITCH_INTERVAL": getattr(sys.modules[__name__], 'SWITCH_INTERVAL', 0.08),
        "UI_DELAY_COMPENSATION": 1.0,
    },
    "TIMEOUTS": {
        "CALENDAR_LOAD": 90,
        "SLOT_LOAD": 10,
        "SAVE_BUTTON": 5,
        "SUMMARY_PAGE": 30,
        "EMAIL_FIELD": 10,
        "PAGE_LOAD": 10,
    },
    "BROWSER": {
        "WIDTH": int(3.8 * 96),   
        "HEIGHT": int(8.5 * 96), 
    }
}

XPATHS = {
    "NAME": "//tr[td[text()='Full name (as per NID/BRC)']]/td[2]",
    "TIME": "//tr[td[text()='Appointment time']]/td[2]",
    "EMAIL_FIELD": "//input[@type='email']",
    "PASSWORD_FIELD": "//input[@type='password']",
    "EMAIL_ACCOUNT": "//input[@type='email']",
    "SAVE_BUTTON": "//span[text()='Save and continue']",
    "NO_SLOTS": "//*[contains(text(), 'No time slots available')]",
    "ERROR_MESSAGES": "error-messages",
    "TIME_SLOTS_CONTAINER": "vbeop-time-slots",
    "TIME_SLOT": "time-slot",
    "CALENDAR": "ngb-dp-content",
}

session_terminated_event = Event()

def display_email_list():
    print("\n" + "="*50)
    print("📧 AVAILABLE EMAIL ACCOUNTS:")
    print("="*50)
    
    for i, email in enumerate(EMAILS, 1):
        print(f"{i}. {email}")
    
    print("="*50)

def get_email_selection():
    while True:
        try:
            selection = input(f"\nSelect 2 emails for Driver 1 and Driver 2 (e.g., '1 2'): ").strip()
            
            if not selection:
                print("❌ Please enter your selection")
                continue
                
            parts = selection.split()
            
            if len(parts) != 2:
                print("❌ Please enter exactly 2 numbers separated by space")
                continue
            
            email1_idx = int(parts[0]) - 1
            email2_idx = int(parts[1]) - 1
            
            if email1_idx < 0 or email1_idx >= len(EMAILS):
                print(f"❌ First number must be between 1 and {len(EMAILS)}")
                continue
                
            if email2_idx < 0 or email2_idx >= len(EMAILS):
                print(f"❌ Second number must be between 1 and {len(EMAILS)}")
                continue
            
            if email1_idx == email2_idx:
                print("❌ Please select different emails for each driver")
                continue
            
            selected_emails = (EMAILS[email1_idx], EMAILS[email2_idx])
            
            print(f"\n✅ Selected emails:")
            print(f"   Driver 1: {selected_emails[0]}")
            print(f"   Driver 2: {selected_emails[1]}")
            
            confirm = input("\nConfirm selection? (y/n): ").strip().lower()
            if confirm in ['y', 'yes']:
                return selected_emails
            else:
                print("Let's try again...")
                continue
                
        except ValueError:
            print("❌ Please enter valid numbers")
        except Exception as e:
            print(f"❌ Error: {e}")

def fill_login_credentials(driver, email, password, driver_id):
    try:
        log_message(f"D{driver_id}: Filling credentials for {email}")
        
        WebDriverWait(driver, CONFIG["TIMEOUTS"]["PAGE_LOAD"]).until(
            EC.presence_of_element_located((By.XPATH, XPATHS["EMAIL_FIELD"]))
        )
        
        email_field = driver.find_element(By.XPATH, XPATHS["EMAIL_FIELD"])
        email_field.clear()
        email_field.send_keys(email)
        
        password_field = driver.find_element(By.XPATH, XPATHS["PASSWORD_FIELD"])
        password_field.clear()
        password_field.send_keys(password)
        
        log_message(f"D{driver_id}: ✅ Credentials filled")
        return True
        
    except Exception as e:
        log_message(f"D{driver_id}: ❌ Failed to fill credentials: {e}", level="error")
        return False

class PassportAutomation:
    def __init__(self, driver_id, delivery_type, email):
        self.driver_id = driver_id
        self.delivery_type = delivery_type
        self.email = email
        self.driver = None
        self.target_day = datetime.strptime(CONFIG["TARGET_DATE_STR"], "%d/%m/%y").day
        self.is_initialized = False
        
    def create_driver(self):
        if self.driver:
            log_message(f"D{self.driver_id}: Driver already exists")
            return self.driver
            
        chrome_options = Options()
        
        if not Path(CONFIG["BRAVE_PATH"]).exists():
            raise FileNotFoundError(f"Browser not found at: {CONFIG['BRAVE_PATH']}")
        
        if not Path(CONFIG["CHROMEDRIVER_PATH"]).exists():
            raise FileNotFoundError(f"ChromeDriver not found at: {CONFIG['CHROMEDRIVER_PATH']}")
        
        chrome_options.binary_location = CONFIG["BRAVE_PATH"]
        
        chrome_options.add_argument(f"--window-size={CONFIG['BROWSER']['WIDTH']},{CONFIG['BROWSER']['HEIGHT']}")
        
        optimization_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage", 
            "--disable-extensions",
            "--disable-plugins",
            "--disable-images",
            "--disable-blink-features=AutomationControlled",
            "--disable-save-password-bubble",
            "--disable-password-manager",
            "--disable-password-generation"
        ]
        
        for arg in optimization_args:
            chrome_options.add_argument(arg)
            
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        
        prefs = {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.notifications": 2
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        try:
            self.driver = webdriver.Chrome(
                service=Service(CONFIG["CHROMEDRIVER_PATH"]), 
                options=chrome_options
            )
            
            if self.driver_id == 1:
                self.driver.set_window_position(0, 0)
            else:
                self.driver.set_window_position(CONFIG['BROWSER']['WIDTH'] + 10, 0)
            
            log_message(f"D{self.driver_id}: Driver created ({CONFIG['BROWSER']['WIDTH']}x{CONFIG['BROWSER']['HEIGHT']})")
            return self.driver
            
        except Exception as e:
            log_message(f"D{self.driver_id}: Driver creation failed: {e}", level="error")
            raise

    def extract_booking_info(self):
        try:
            WebDriverWait(self.driver, CONFIG["TIMEOUTS"]["SUMMARY_PAGE"]).until(
                EC.presence_of_element_located((By.XPATH, XPATHS["NAME"]))
            )
            
            name = self.driver.find_element(By.XPATH, XPATHS["NAME"]).text.strip()
            raw_time = self.driver.find_element(By.XPATH, XPATHS["TIME"]).text.strip()
            
            date_part = " ".join(raw_time.split(",")[0].split()[:2])
            time_part = raw_time.split(",")[1].strip()
            appointment_time = f"{date_part}, {time_part}"

            email = self._extract_email()
            
            return name, appointment_time, email
            
        except Exception as e:
            log_message(f"D{self.driver_id}: Info extraction failed: {e}", level="error")
            return "Unknown", "Unknown", "Unknown"

    def _extract_email(self):
        try:
            self.driver.get("https://www.epassport.gov.bd/home/account/edit")
            time.sleep(2)
            
            email_element = WebDriverWait(self.driver, CONFIG["TIMEOUTS"]["EMAIL_FIELD"]).until(
                EC.presence_of_element_located((By.XPATH, XPATHS["EMAIL_ACCOUNT"]))
            )
            return email_element.get_attribute("value").strip()
            
        except TimeoutException:
            log_message(f"D{self.driver_id}: Email field not found", level="warning")
            return self.email

    def send_telegram_notification(self, name, time_str, email):
        message = f"Name: {name}\nTime: {time_str}\nEmail: {email}"
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        
        success = False
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
                    success = True
                else:
                    log_message(f"D{self.driver_id}: Telegram failed to {chat_id}", level="error")
            except Exception as e:
                log_message(f"D{self.driver_id}: Telegram error: {e}", level="error")
        
        return success

    def send_fallback_notification(self):
        try:
            message = f"Passport slot booked at {datetime.now().strftime('%H:%M:%S')}. Check browser for details."
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            
            for chat_id in TELEGRAM_CHAT_IDS:
                payload = {"chat_id": chat_id, "text": message}
                requests.post(url, data=payload, timeout=5)
            
            log_message(f"D{self.driver_id}: Fallback telegram sent")
            return True
        except Exception:
            log_message(f"D{self.driver_id}: All telegram failed", level="error")
            return False

    def is_in_hot_window(self):
        seconds = datetime.now().second
        return (seconds >= CONFIG["HOT_WINDOW"]["START_SEC"] or 
                seconds <= CONFIG["HOT_WINDOW"]["END_SEC"])

    def get_hot_window_remaining_time(self):
        seconds = datetime.now().second
        
        if seconds >= CONFIG["HOT_WINDOW"]["START_SEC"]:
            return (60 - seconds) + CONFIG["HOT_WINDOW"]["END_SEC"]
        elif seconds <= CONFIG["HOT_WINDOW"]["END_SEC"]:
            return CONFIG["HOT_WINDOW"]["END_SEC"] - seconds
        else:
            return 0

    def wait_for_hot_window(self):
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
        try:
            xpath = CONFIG["DELIVERY_TYPES"][delivery_type]
            element = self.driver.find_element(By.XPATH, xpath)
            self.driver.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            return False

    def quick_error_check(self):
        try:
            errors = self.driver.find_elements(By.CLASS_NAME, XPATHS["ERROR_MESSAGES"])
            return len(errors) > 0
        except Exception:
            return False

    def check_no_slots_message(self):
        try:
            no_slots = self.driver.find_elements(By.XPATH, XPATHS["NO_SLOTS"])
            return len(no_slots) > 0
        except Exception:
            return False

    def initialize_calendar(self):
        if self.is_initialized:
            return True
            
        try:
            WebDriverWait(self.driver, CONFIG["TIMEOUTS"]["CALENDAR_LOAD"]).until(
                EC.presence_of_element_located((By.CLASS_NAME, XPATHS["CALENDAR"]))
            )
            log_message(f"D{self.driver_id}: Calendar loaded")
            
            if not self.fast_click_delivery_option(self.delivery_type):
                log_message(f"D{self.driver_id}: Initial delivery click failed", level="error")
                return False
                
            self.is_initialized = True
            return True
            
        except TimeoutException:
            log_message(f"D{self.driver_id}: Calendar timeout", level="error")
            return False

    def rapid_switching_in_hot_window(self):
        log_message(f"D{self.driver_id}: HOT WINDOW")
        
        delivery_options = ["Regular delivery", "Express delivery"]
        current_option = self.driver_id % 2
        
        start_time = time.time()
        remaining_time = self.get_hot_window_remaining_time()
        switch_count = 0
        
        delivery_xpaths = [CONFIG["DELIVERY_TYPES"][opt] for opt in delivery_options]
        date_xpath = f"//div[@class='btn-light' and text()='{self.target_day}']"
        
        while ((time.time() - start_time) < remaining_time and 
               not session_terminated_event.is_set()):
            
            current_delivery = delivery_options[current_option]
            
            try:
                element = self.driver.find_element(By.XPATH, delivery_xpaths[current_option])
                self.driver.execute_script("arguments[0].click();", element)
                switch_count += 1
                
                if switch_count % 60 == 0:
                    log_message(f"D{self.driver_id}: {switch_count} switches")
                    if self.quick_error_check():
                        log_message(f"D{self.driver_id}: Error box detected")
                        return False, None
                
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
                pass 
            
            current_option = 1 - current_option
            time.sleep(CONFIG["HOT_WINDOW"]["RAPID_SWITCH_INTERVAL"])
        
        log_message(f"D{self.driver_id}: Window ended - {switch_count} switches")
        return False, None

    def _check_and_click_date(self, date_xpath, current_delivery):
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
        try:
            timestamp = datetime.now().strftime("%H%M%S")
            self.driver.save_screenshot(f"D{self.driver_id}_{timestamp}.png")
        except Exception:
            pass

    def handle_slot_selection(self):
        try:
            log_message(f"D{self.driver_id}: Loading slots")
            
            time_slots_container = WebDriverWait(self.driver, CONFIG["TIMEOUTS"]["SLOT_LOAD"]).until(
                EC.presence_of_element_located((By.CLASS_NAME, XPATHS["TIME_SLOTS_CONTAINER"]))
            )
            
            if self.check_no_slots_message():
                log_message(f"D{self.driver_id}: No slots - ending session")
                session_terminated_event.set()
                return False
            
            time_slot_labels = time_slots_container.find_elements(By.CLASS_NAME, XPATHS["TIME_SLOT"])
            
            if not time_slot_labels:
                log_message(f"D{self.driver_id}: No slot elements")
                session_terminated_event.set()
                return False
            
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
        try:
            save_button = WebDriverWait(self.driver, CONFIG["TIMEOUTS"]["SAVE_BUTTON"]).until(
                EC.element_to_be_clickable((By.XPATH, XPATHS["SAVE_BUTTON"]))
            )
            self.driver.execute_script("arguments[0].click();", save_button)
            log_message(f"D{self.driver_id}: Save clicked")
            
            time.sleep(1)
            if self.quick_error_check():
                log_message(f"D{self.driver_id}: Slot taken - trying next window")
                return False 
            
            self._play_success_sound()
            
            WebDriverWait(self.driver, CONFIG["TIMEOUTS"]["SUMMARY_PAGE"]).until(
                EC.url_matches(r"https://www.epassport.gov.bd/applications/application-form/.*/summary")
            )
            log_message(f"D{self.driver_id}: SUCCESS - Summary loaded")
            
            self._send_success_notifications()
            
            session_terminated_event.set()
            return True
            
        except Exception as e:
            log_message(f"D{self.driver_id}: Save process failed: {e}", level="error")
            return False

    def _play_success_sound(self):
        try:
            sound_path = CONFIG["SOUND_PATHS"]["success"]
            if sound_path and Path(sound_path).exists():
                subprocess.run(["afplay", sound_path], check=False)
        except Exception:
            pass

    def _send_success_notifications(self):
        try:
            name, appointment_time, email = self.extract_booking_info()
            
            if self.send_telegram_notification(name, appointment_time, email):
                log_message(f"D{self.driver_id}: Telegram sent - DONE")
            else:
                log_message(f"D{self.driver_id}: Telegram failed but booking successful")
                
        except Exception as e:
            log_message(f"D{self.driver_id}: Notification error: {e}", level="error")
            self.send_fallback_notification()

    def run_automation(self):
        try:
            if not self.initialize_calendar():
                return
        
            while not session_terminated_event.is_set():
                self.wait_for_hot_window()
                
                if session_terminated_event.is_set():
                    break
                
                success, delivery = self.rapid_switching_in_hot_window()
                
                if success:
                    if self.handle_slot_selection():
                        if self.process_booking_success():
                            break
                else:
                    log_message(f"D{self.driver_id}: No date found")
                
                time.sleep(1)
                
        except Exception as e:
            log_message(f"D{self.driver_id}: Automation error: {e}", level="error")
            session_terminated_event.set()
        finally:
            self.cleanup()

    def cleanup(self):
        try:
            if self.driver:
                log_message(f"D{self.driver_id}: Cleaning up")
                self.driver.quit()
                self.driver = None
        except Exception as e:
            log_message(f"D{self.driver_id}: Cleanup error: {e}", level="warning")

def run_automation_thread(automation):
    try:
        automation.run_automation()
    except Exception as e:
        log_message(f"D{automation.driver_id}: Thread error: {e}", level="error")
        session_terminated_event.set()
    finally:
        log_message(f"D{automation.driver_id}: Thread completed")

def main():
    log_message("Starting passport slot booking automation")
    
    display_email_list()
    selected_emails = get_email_selection()
    
    automations = []
    
    try:
        automation1 = PassportAutomation(1, "Regular delivery", selected_emails[0])
        automation2 = PassportAutomation(2, "Express delivery", selected_emails[1])
        automations = [automation1, automation2]
        
        automation1.create_driver()
        automation2.create_driver()
        
        automation1.driver.get("https://www.epassport.gov.bd/authorization/login")
        automation2.driver.get("https://www.epassport.gov.bd/authorization/login")
        log_message("Login pages opened")

        log_message("\n🔐 Filling login credentials...")
        
        fill_success1 = fill_login_credentials(
            automation1.driver, 
            selected_emails[0], 
            EMAIL_PASSWORD, 
            1
        )
        
        fill_success2 = fill_login_credentials(
            automation2.driver, 
            selected_emails[1], 
            EMAIL_PASSWORD, 
            2
        )
        
        if not fill_success1 or not fill_success2:
            log_message("Failed to fill credentials for one or both drivers", level="error")
            return
        
        log_message("\n✅ Credentials filled for both drivers")
        log_message("👆 Please solve captcha and login manually for both browsers")
        log_message("📋 Then navigate to delivery options page")

        input("\nPress ENTER after login and navigation to delivery options page...")

        thread1 = threading.Thread(target=run_automation_thread, args=(automation1,))
        thread2 = threading.Thread(target=run_automation_thread, args=(automation2,))

        log_message("Starting automation threads...")
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
        session_terminated_event.set()
    finally:
        for automation in automations:
            automation.cleanup()
        log_message("Cleanup completed - Exit")

if __name__ == "__main__":
    main()