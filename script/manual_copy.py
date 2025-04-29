import time
import os
import threading
import platform
import subprocess
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
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import random

# Platform-specific sound playing
def play_sound(sound_type):
    system = platform.system()
    
    sounds = {
        "alert": "/System/Library/Sounds/Glass.aiff" if system == "Darwin" else "notification.wav",
        "error": "/System/Library/Sounds/Funk.aiff" if system == "Darwin" else "error.wav",
        "success": "/System/Library/Sounds/Hero.aiff" if system == "Darwin" else "success.wav"
    }
    
    if sound_type in sounds:
        sound_file = sounds[sound_type]
        try:
            if system == "Darwin":  # macOS
                subprocess.run(["afplay", sound_file], check=False)
            elif system == "Windows":
                import winsound
                winsound.PlaySound(sound_file, winsound.SND_FILENAME)
            elif system == "Linux":
                subprocess.run(["paplay", sound_file], check=False)
        except Exception as e:
            print(f"Failed to play sound: {e}")

# Push notification function
def send_notification(title, message):
    system = platform.system()
    try:
        if system == "Darwin":  # macOS
            os.system(f"""osascript -e 'display notification "{message}" with title "{title}"'""")
        # elif system == "Windows":
        #     from win10toast import ToastNotifier
        #     toaster = ToastNotifier()
        #     toaster.show_toast(title, message, duration=5)
        elif system == "Linux":
            subprocess.run(["notify-send", title, message], check=False)
    except Exception as e:
        print(f"Failed to send notification: {e}")

class PassportAutomation:
    def __init__(self, target_date_str=datetime.now().strftime("%d/%m/%y")):
        self.chrome_options = Options()
        self.chrome_options.binary_location = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
        self.service = Service("/opt/homebrew/bin/chromedriver")
        
        # Add performance optimizations
        self.chrome_options.add_argument("--disable-extensions")
        self.chrome_options.add_argument("--disable-gpu")
        self.chrome_options.add_argument("--no-sandbox")
        self.chrome_options.add_argument("--disable-dev-shm-usage")
        self.chrome_options.add_argument("--disable-features=NetworkService")
        self.chrome_options.add_argument("--dns-prefetch-disable")
        self.chrome_options.add_argument("--disable-browser-side-navigation")
        
        self.driver = webdriver.Chrome(service=self.service, options=self.chrome_options)
        
        # Create folder using hour_minute format
        current_time = datetime.now()
        self.run_folder = current_time.strftime("%H_%M")
        
        # Create run folder
        os.makedirs(self.run_folder, exist_ok=True)
        
        # Set up logging
        self.LOG_FILE = os.path.join(self.run_folder, f"log.txt")
        with open(self.LOG_FILE, "w") as log_file:
            log_file.write("=== Automation Log Start ===\n")
        
        # Parse target date
        self.target_date_str = target_date_str
        self.target_date = datetime.strptime(target_date_str, "%d/%m/%y")
        self.target_day = self.target_date.day
        
        # Delivery options
        self.delivery_types = {
            "Regular delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.REGULAR']",
            "Express delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.EXPRESS']"
        }
        
        # Flags for control flow
        self.date_found = False
        self.checking_delivery_option = "Regular delivery"
        self.last_option_switch_time = 0
        self.option_check_interval = 4.0  # Reduced to 1 second for faster switching
        self.date_available = False
        self.stop_threads = False

    def log_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        formatted_message = f"[{timestamp}] {message.split(' ')[0]}: {message}"
        print(formatted_message)
        with open(self.LOG_FILE, "a") as log_file:
            log_file.write(f"{formatted_message}\n")

    def wait_for_element(self, locator, timeout=10):
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located(locator)
            )
        except TimeoutException:
            self.log_message(f"❌ Timeout waiting for element: {locator}")
            return None

    def wait_for_clickable_element(self, locator, timeout=10):
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable(locator)
            )
        except TimeoutException:
            self.log_message(f"❌ Timeout waiting for clickable element: {locator}")
            return None

    def click_element(self, locator, scroll=True, timeout=10):
        try:
            element = self.wait_for_clickable_element(locator, timeout)
            if element:
                if scroll:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                    time.sleep(0.1)  # Small pause for scroll to complete
                element.click()
                return True
            return False
        except Exception as e:
            self.log_message(f"❌ Error clicking element: {locator}, {e}")
            return False

    def check_for_errors(self):
        error_message_container = self.driver.find_elements(By.CLASS_NAME, "error-messages")
        if error_message_container:
            self.log_message("❌ Error message detected on the page.")
            return True
        return False

    def handle_failure_and_retry(self):
        self.log_message("🔄 Retry...")
        play_sound("error")
        self.driver.refresh()
        time.sleep(2)

    def switch_delivery_option(self):
        next_delivery = "Express delivery" if self.checking_delivery_option == "Regular delivery" else "Regular delivery"
        if time.time() - self.last_option_switch_time < self.option_check_interval:
            return self.checking_delivery_option
        if self.click_element((By.XPATH, self.delivery_types[next_delivery])):
            self.log_message(f"✅ Switched to '{next_delivery}'")
            self.checking_delivery_option = next_delivery
            self.last_option_switch_time = time.time()
            time.sleep(0.5)
        return self.checking_delivery_option

    def check_for_target_date(self):
        """Thread function to continuously check for the target date."""
        date_first_seen_time = 0
        # Make script more aggressive in finding dates
        while not self.stop_threads:
            try:
                date_xpath = f"//div[@class='btn-light' and text()='{self.target_day}']"
                date_elements = self.driver.find_elements(By.XPATH, date_xpath)
                found_enabled_date = False
                for date_element in date_elements:
                    is_disabled = ("disabled" in date_element.get_attribute("class") or 
                                   date_element.get_attribute("aria-disabled") == "true")
                    if not is_disabled:
                        found_enabled_date = True
                        if not self.date_available:
                            self.date_available = True
                            date_first_seen_time = time.time()
                            play_sound("alert")
                            self.log_message(f"🔔 Date {self.target_day} detected under '{self.checking_delivery_option}'")
                        time_since_date_seen = time.time() - date_first_seen_time
                        if time_since_date_seen >= 0.7:
                            try:
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", date_element)
                                self.driver.execute_script("arguments[0].click();", date_element)
                                if not self.check_for_errors():
                                    self.log_message(f"✅ Clicked date {self.target_day}")
                                    play_sound("success")
                                    self.date_found = True
                                    return
                                else:
                                    self.date_available = False
                            except Exception:
                                self.date_available = False
                                self.switch_delivery_option()
                if not found_enabled_date:
                    if self.date_available:
                        self.switch_delivery_option()
                    self.date_available = False
                if not self.date_found and not self.date_available and (time.time() - self.last_option_switch_time >= self.option_check_interval):
                    self.switch_delivery_option()
                time.sleep(0.2)
            except Exception:
                time.sleep(0.3)

    def select_time_slot(self):
        try:
            time_slots_container = self.wait_for_element((By.CLASS_NAME, "vbeop-time-slots"), timeout=7)
            if not time_slots_container:
                time_slot_labels = self.driver.find_elements(By.CLASS_NAME, "time-slot")
                if not time_slot_labels:
                    return False
            else:
                time_slot_labels = time_slots_container.find_elements(By.CLASS_NAME, "time-slot")
                if not time_slot_labels:
                    return False
            slot_to_select = time_slot_labels[0]
            slot_text = slot_to_select.text
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", slot_to_select)
                self.driver.execute_script("arguments[0].click();", slot_to_select)
                self.log_message(f"✅ Slot '{slot_text}' selected")
                return True
            except Exception:
                try:
                    slot_to_select.click()
                    self.log_message(f"✅ Slot '{slot_text}' selected")
                    return True
                except Exception:
                    return False
        except Exception:
            return False

    def complete_booking(self):
        try:
            save_button_xpath = "//span[text()='Save and continue']"
            save_button = self.driver.find_element(By.XPATH, save_button_xpath)
            try:
                self.driver.execute_script("arguments[0].click();", save_button)
            except:
                save_button.click()
            try:
                WebDriverWait(self.driver, 20).until(
                    EC.url_matches(r"https://www.epassport.gov.bd/applications/application-form/.*/summary")
                )
                self.driver.save_screenshot(f"{self.run_folder}/schedule.png")
                play_sound("success")
                time.sleep(2)
                self.driver.get("https://www.epassport.gov.bd/home/account/edit")
                self.log_message("✅ Booking saved and summary loaded")
                return True
            except TimeoutException:
                return False
        except Exception:
            return False

    def run(self):
        self.driver.get("https://www.epassport.gov.bd/authorization/login")
        self.log_message("🌐 Opened the login page")
        input("Press ENTER after logging in to start the automation...")
        play_sound("alert")
        self.driver.execute_script("""
            document.body.style.setProperty('--ngb-slide-transition-duration', '0.1s');
            var styles = document.createElement('style');
            styles.innerHTML = '* { transition-duration: 0.1s !important; animation-duration: 0.1s !important; }';
            document.head.appendChild(styles);
        """)
        date_checker_thread1 = threading.Thread(target=self.check_for_target_date)
        date_checker_thread1.daemon = True
        date_checker_thread1.start()
        date_checker_thread2 = threading.Thread(target=self.check_for_target_date)
        date_checker_thread2.daemon = True
        date_checker_thread2.start()
        self.wait_for_element((By.CLASS_NAME, "ngb-dp-content"), timeout=60)
        self.log_message("📅 Calendar loaded successfully")
        retry_count = 0
        while not self.date_found:
            time.sleep(0.2)
            if self.date_available and not self.date_found:
                if self.select_time_slot():
                    if self.complete_booking():
                        self.log_message("🎉 Booking successful. Closing.")
                        break
                    else:
                        retry_count += 1
                        self.driver.refresh()
                        self.date_found = False
                        self.date_available = False
                        time.sleep(0.5)
                else:
                    retry_count += 1
                    if retry_count > 3:
                        self.log_message("🔄 Retry...")
                        self.driver.refresh()
                        retry_count = 0
                        time.sleep(1)
                    self.date_found = False
                    self.date_available = False
        self.stop_threads = True
        try:
            date_checker_thread1.join(timeout=1)
            date_checker_thread2.join(timeout=1)
        except:
            pass
        play_sound("success")
        play_sound("success")
        input("🎉 SUCCESS! Press ENTER to close the browser...")
        self.driver.quit()

if __name__ == "__main__":
    # Create and run the automation
    automation = PassportAutomation()
    automation.run()