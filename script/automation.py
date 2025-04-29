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
        "alert": (
            "/System/Library/Sounds/Glass.aiff"
            if system == "Darwin"
            else "notification.wav"
        ),
        "error": (
            "/System/Library/Sounds/Funk.aiff" if system == "Darwin" else "error.wav"
        ),
        "success": (
            "/System/Library/Sounds/Hero.aiff" if system == "Darwin" else "success.wav"
        ),
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
            os.system(
                f"""osascript -e 'display notification "{message}" with title "{title}"'"""
            )
        elif system == "Linux":
            subprocess.run(["notify-send", title, message], check=False)
    except Exception as e:
        print(f"Failed to send notification: {e}")


class PassportAutomation:
    def __init__(self, target_date_str=datetime.now().strftime("%d/%m/%y")):
        # target_date_str = "10/08/25"
        self.chrome_options = Options()
        self.chrome_options.binary_location = (
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
        )
        self.service = Service("/opt/homebrew/bin/chromedriver")
        self.driver = webdriver.Chrome(
            service=self.service, options=self.chrome_options
        )

        current_time = datetime.now()
        self.run_folder = current_time.strftime("%H_%M")

        os.makedirs(self.run_folder, exist_ok=True)

        self.LOG_FILE = os.path.join(self.run_folder, f"log.txt")
        with open(self.LOG_FILE, "w") as log_file:
            log_file.write("=== Automation Log Start ===\n")

        self.target_date_str = target_date_str
        self.target_date = datetime.strptime(target_date_str, "%d/%m/%y")
        self.target_day = self.target_date.day

        self.delivery_types = {
            "Regular delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.REGULAR']",
            "Express delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.EXPRESS']",
        }

        self.date_found = False
        self.checking_delivery_option = "Regular delivery"
        self.last_option_switch_time = 0
        self.option_check_interval = 6  # seconds to check each option before switching
        self.date_available = False
        self.stop_threads = False

    def log_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        formatted_message = f"[{timestamp}] {message}"
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
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});", element
                    )
                    time.sleep(0.1)
                element.click()
                return True
            return False
        except Exception as e:
            self.log_message(f"❌ Error clicking element: {locator}, {e}")
            return False

    def check_for_errors(self):
        error_message_container = self.driver.find_elements(
            By.CLASS_NAME, "error-messages"
        )
        if error_message_container:
            self.log_message("❌ Error message detected on the page.")
            return True
        return False

    def handle_failure_and_retry(self):
        self.log_message("🔄 Refreshing the page to retry...")
        play_sound("error")
        self.driver.refresh()
        time.sleep(2)

    def switch_delivery_option(self):
        next_delivery = (
            "Express delivery"
            if self.checking_delivery_option == "Regular delivery"
            else "Regular delivery"
        )
        if time.time() - self.last_option_switch_time < self.option_check_interval:
            return self.checking_delivery_option

        # self.log_message(f"🔄 Switching to {next_delivery} option")

        if self.click_element((By.XPATH, self.delivery_types[next_delivery])):
            self.log_message(f"✅ Switched to '{next_delivery}'")
            self.checking_delivery_option = next_delivery
            self.last_option_switch_time = time.time()
            time.sleep(0.5)
        else:
            self.log_message(f"⚠️ Failed to switch to '{next_delivery}'")

        return self.checking_delivery_option

    def check_for_target_date(self):
        """Thread function to continuously check for the target date."""
        date_first_seen_time = 0
        while not self.stop_threads:
            try:
                # Check if date is present and clickable
                date_xpath = f"//div[@class='btn-light' and text()='{self.target_day}']"
                date_elements = self.driver.find_elements(By.XPATH, date_xpath)

                found_enabled_date = False
                for date_element in date_elements:
                    if "disabled" not in date_element.get_attribute("class"):
                        found_enabled_date = True

                        # If this is the first time we've seen the date available in this option
                        if not self.date_available:
                            self.date_available = True
                            date_first_seen_time = time.time()
                            self.log_message(
                                f"👀 Target date {self.target_day} detected under '{self.checking_delivery_option}'!"
                            )
                            # Don't try to click immediately - give it time to become fully clickable

                        # Calculate how long we've seen the date available
                        time_since_date_seen = time.time() - date_first_seen_time

                        # Only try clicking after waiting for 1.5 seconds for the element to be properly clickable
                        # This handles the 2-5 second delay you mentioned
                        if time_since_date_seen >= 1.5:
                            self.log_message(
                                f"🔍 Attempting to click date after {time_since_date_seen:.1f}s wait"
                            )
                            try:
                                # Try to click it after the wait period
                                self.driver.execute_script(
                                    "arguments[0].scrollIntoView({block: 'center'});",
                                    date_element,
                                )
                                date_element.click()

                                if not self.check_for_errors():
                                    self.log_message(
                                        f"✅ Successfully clicked date {self.target_day} under '{self.checking_delivery_option}'"
                                    )
                                    self.date_found = True
                                    return
                                else:
                                    # Reset if there was an error
                                    self.date_available = False
                            except Exception as e:
                                self.log_message(f"❌ Failed to click date: {e}")
                                # If we've waited more than 4 seconds and still can't click, reset and try other option
                                if time_since_date_seen > 4:
                                    self.log_message(
                                        "⚠️ Date remained unclickable for too long, switching options"
                                    )
                                    self.date_available = False

                # If date is not visible at all, reset the available flag
                if not found_enabled_date:
                    self.date_available = False

                # If date is not available or click failed, switch delivery option after the interval
                if not self.date_found and (
                    time.time() - self.last_option_switch_time
                    >= self.option_check_interval
                ):
                    self.switch_delivery_option()

                time.sleep(0.3)

            except Exception as e:
                self.log_message(f"❌ Error in date checking thread: {e}")
                time.sleep(0.5)

    def select_time_slot(self):
        try:
            self.log_message("⏳ Waiting for time slots...")
            time_slots_container = self.wait_for_element(
                (By.CLASS_NAME, "vbeop-time-slots"), timeout=15
            )

            if not time_slots_container:
                self.log_message("❌ Time slots container not found")
                return False

            time_slot_labels = time_slots_container.find_elements(
                By.CLASS_NAME, "time-slot"
            )

            if not time_slot_labels:
                self.log_message("❌ No time slots available")
                return False

            enabled_slots = []
            for slot in time_slot_labels:
                try:
                    associated_input = self.driver.find_element(
                        By.ID, slot.get_attribute("for")
                    )
                    if associated_input.is_enabled():
                        enabled_slots.append(slot)
                except Exception:
                    continue

            if not enabled_slots:
                self.log_message("❌ No enabled time slots found")
                return False

            slot_to_select = enabled_slots[0]
            slot_text = slot_to_select.text

            self.log_message(f"⏰ Selecting time slot: {slot_text}")
            try:
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", slot_to_select
                )
                slot_to_select.click()

                if self.check_for_errors():
                    self.log_message("❌ Error after selecting time slot")
                    return False

                self.log_message(f"✅ Slot '{slot_text}' selected successfully")
                return True
            except Exception as e:
                self.log_message(f"❌ Error clicking time slot: {e}")
                return False

        except Exception as e:
            self.log_message(f"❌ Error in time slot selection: {e}")
            return False

    def complete_booking(self):
        try:
            save_button_xpath = "//span[text()='Save and continue']"
            if not self.click_element((By.XPATH, save_button_xpath), timeout=20):
                self.log_message("❌ Failed to click 'Save and continue' button")
                return False

            self.log_message("✅ Clicked 'Save and Continue' button")

            if self.check_for_errors():
                self.log_message("❌ Error after clicking 'Save and continue'")
                return False

            try:
                WebDriverWait(self.driver, 30).until(
                    EC.url_matches(
                        r"https://www.epassport.gov.bd/applications/application-form/.*/summary"
                    )
                )
                self.log_message("✅ Summary page loaded successfully")

                self.driver.save_screenshot(f"{self.run_folder}/schedule.png")

                play_sound("success")
                play_sound("success")

                time.sleep(3)

                self.driver.get("https://www.epassport.gov.bd/home/account/edit")
                self.log_message("✅ Navigated to account edit page")

                return True
            except TimeoutException:
                self.log_message("❌ Timeout waiting for summary page")
                return False

        except Exception as e:
            self.log_message(f"❌ Error in booking completion: {e}")
            return False

    def run(self):
        self.driver.get("https://www.epassport.gov.bd/authorization/login")
        self.log_message("🌐 Opened the login page")

        input("Press ENTER after logging in to start the automation...")

        date_checker_thread = threading.Thread(target=self.check_for_target_date)
        date_checker_thread.daemon = True
        date_checker_thread.start()

        self.wait_for_element((By.CLASS_NAME, "ngb-dp-content"), timeout=90)
        self.log_message("📅 Calendar loaded successfully")

        while not self.date_found:
            time.sleep(0.5)
            if self.date_available and not self.date_found:
                if self.select_time_slot():
                    if self.complete_booking():
                        break
                    else:
                        self.log_message("❌ Booking completion failed, retrying...")
                        self.handle_failure_and_retry()
                        self.date_found = False
                        self.date_available = False
                else:
                    self.log_message("❌ Time slot selection failed, retrying...")
                    self.handle_failure_and_retry()
                    self.date_found = False
                    self.date_available = False

        self.stop_threads = True
        if date_checker_thread.is_alive():
            date_checker_thread.join(timeout=1)

        input("Press ENTER to close the browser...")
        self.driver.quit()
        self.log_message("🛑 Browser closed successfully")


if __name__ == "__main__":
    automation = PassportAutomation()
    automation.run()
