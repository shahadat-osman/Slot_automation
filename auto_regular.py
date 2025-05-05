import time
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import random

# Constants
BOOKING_URL = "https://www.epassport.gov.bd/authorization/login"
SOUND_SUCCESS = "/System/Library/Sounds/Glass.aiff"
SOUND_ALERT = "/System/Library/Sounds/Funk.aiff"

# Configuration - You can modify these values as needed
SWITCH_INTERVAL = 5  # Seconds between delivery option switches (change this value as needed)
BROWSER_RESTART_INTERVAL = 15 * 60  # Restart browser every 15 minutes to reduce memory leakage
LOW_RESOURCE_MODE = True  # Set to True to reduce browser resource usage (helps with overheating)

class PassportBooker:
    def __init__(self):
        """Initialize the passport booking automation"""
        self.run_id = random.randint(1000, 9999)
        self.run_folder = f"run_{self.run_id}"
        os.makedirs(self.run_folder, exist_ok=True)
        
        self.log_file = os.path.join(self.run_folder, f"log-{self.run_id}.txt")
        with open(self.log_file, "w") as log:
            log.write(f"=== Booking Automation Started: {datetime.now()} ===\n")
        
        self.setup_browser()
        self.current_delivery = "Regular delivery"
        self.target_day = datetime.now().day
        
    def setup_browser(self):
        """Setup the browser with optimized settings"""
        options = Options()
        options.binary_location = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
        
        # Performance and resource optimizations
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-browser-side-navigation")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        
        if LOW_RESOURCE_MODE:
            # Critical resource reduction settings
            options.add_argument("--disable-logging")
            options.add_argument("--log-level=3")  # ERROR level only
            options.add_argument("--disable-javascript-harmony-shipping")
            options.add_argument("--disable-breakpad")  # Disable crash reporting
            options.add_argument("--disable-features=NetworkPrediction")
            options.add_argument("--disable-features=MediaRouter")
            options.add_argument("--disable-site-isolation-trials")
            options.add_argument("--disable-web-security")  # Only for this automation purpose
            options.add_argument("--process-per-site")  # Reduce process count
            options.add_argument("--lite-mode")  # Data saving mode
            options.add_argument("--blink-settings=imagesEnabled=false")  # Disable images
            options.add_experimental_option("prefs", {
                "profile.default_content_setting_values.images": 2,  # Disable images
                "profile.managed_default_content_settings.images": 2,
                "profile.default_content_setting_values.notifications": 2,  # Disable notifications
                "profile.managed_default_content_settings.javascript": 1,  # Keep JS enabled
                "profile.default_content_setting_values.cookies": 1,  # Accept cookies
            })
            self.log("🔋 Low resource mode enabled to reduce CPU/memory usage")
        
        service = Service("/opt/homebrew/bin/chromedriver")
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.set_page_load_timeout(30)
        
    def log(self, message):
        """Log message to console and file"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        
        with open(self.log_file, "a") as log:
            log.write(f"[{timestamp}] {message}\n")
            
        # Play sound for important messages
        if "SUCCESSFUL" in message:
            for _ in range(3):
                os.system(f"afplay {SOUND_SUCCESS}")
        elif any(x in message for x in ["❌", "⚠️"]):
            os.system(f"afplay {SOUND_ALERT}")
            
    def wait_for(self, locator, timeout=10):
        """Smart wait function with shorter default timeout"""
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located(locator)
            )
        except Exception:
            return None
    
    def click_js(self, element):
        """Fast JavaScript click"""
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        self.driver.execute_script("arguments[0].click();", element)
        
    def switch_delivery_option(self):
        """Switch between delivery options with optimized lookup"""
        delivery_types = {
            "Regular delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.REGULAR']",
            "Express delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.EXPRESS']"
        }
        
        alternate = "Express delivery" if self.current_delivery == "Regular delivery" else "Regular delivery"
        
        try:
            switch_element = self.driver.find_element(By.XPATH, delivery_types[alternate])
            self.click_js(switch_element)
            self.log(f"↔️ Switched to '{alternate}'")
            self.current_delivery = alternate
            return True
        except Exception:
            self.log("⚠️ Switch failed")
            return False
            
    def find_date(self):
        """Find available date efficiently"""
        try:
            date_elements = self.driver.find_elements(
                By.XPATH, f"//div[@class='btn-light' and text()='{self.target_day}']"
            )
            
            for date in date_elements:
                if "disabled" not in date.get_attribute("class"):
                    self.log(f"✅ Date {self.target_day} available - {self.current_delivery}!")
                    return date
            return None
        except Exception:
            self.log("⚠️ Date check error")
            return None
            
    def select_time_slot(self):
        """Select available time slot with optimized approach"""
        try:
            # Wait for slots to appear with shorter timeout
            slots_container = self.wait_for((By.CLASS_NAME, "vbeop-time-slots"), timeout=5)
            if not slots_container:
                return False
                
            # Find all enabled slots
            enabled_slots = []
            for slot in slots_container.find_elements(By.CLASS_NAME, "time-slot"):
                try:
                    input_id = slot.get_attribute("for")
                    if input_id:
                        input_element = self.driver.find_element(By.ID, input_id)
                        if input_element.is_enabled():
                            enabled_slots.append((slot, slot.text))
                except:
                    continue
                    
            if not enabled_slots:
                self.log("⚠️ No enabled slots")
                return False
                
            # Sort by time and select preferred slot
            enabled_slots.sort(key=lambda x: x[1])
            
            # Prefer earlier slots (first half) with 80% probability for better chances
            if random.random() < 0.8:
                first_half = enabled_slots[:max(1, len(enabled_slots) // 2)]
                selected_slot, time_text = random.choice(first_half)
                self.log(f"🎯 Selected earlier slot: {time_text}")
            else:
                selected_slot, time_text = random.choice(enabled_slots)
                self.log(f"🎲 Selected slot: {time_text}")
                
            # Click slot and continue
            self.click_js(selected_slot)
            
            # Find and click save button
            save_button = self.driver.find_element(By.XPATH, "//span[text()='Save and continue']")
            self.click_js(save_button)
            self.log("✅ Saved slot selection")
            return True
            
        except Exception as e:
            self.log(f"❌ Slot selection error")
            return False
            
    def check_booking_success(self):
        """Check if booking was successful"""
        try:
            # Check URL contains summary - faster than regex
            WebDriverWait(self.driver, 5).until(
                lambda d: "summary" in d.current_url
            )
            self.log("✅ BOOKING SUCCESSFUL! 🎉")
            self.driver.save_screenshot(f"{self.run_folder}/success-{self.run_id}.png")
            
            # Navigate to account page
            self.driver.get("https://www.epassport.gov.bd/home/account/edit")
            self.log("✅ Navigated to account page")
            return True
        except Exception:
            return False
            
    def handle_failure(self):
        """Handle failures with quick refresh"""
        self.log("🔄 Refreshing page")
        self.driver.refresh()
        time.sleep(1)  # Minimal wait
        
    def run(self):
        """Main execution loop"""
        self.driver.get(BOOKING_URL)
        self.log("🌐 Opened login page")
        input("Log in and press ENTER when ready...")
        
        self.wait_for((By.CLASS_NAME, "ngb-dp-content"), timeout=30)
        self.log("📅 Calendar loaded")
        
        # Select initial delivery option
        self.driver.find_element(
            By.XPATH, 
            "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.REGULAR']"
        ).click()
        
        # Initialize timing variables
        last_switch_time = time.time()
        last_restart_time = time.time()
        empty_checks = 0
        
        self.log(f"🔄 Using {SWITCH_INTERVAL}-second interval for delivery option switching")
        
        # Main booking loop
        while True:
            # Check for browser health and restart if needed
            if time.time() - last_restart_time > BROWSER_RESTART_INTERVAL:  # Default 15 minutes
                self.log("🔄 Restarting browser to prevent memory leaks")
                cookies = self.driver.get_cookies()
                self.driver.quit()
                
                self.setup_browser()
                self.driver.get(BOOKING_URL)
                
                for cookie in cookies:
                    try:
                        self.driver.add_cookie(cookie)
                    except:
                        pass
                        
                self.driver.refresh()
                self.wait_for((By.CLASS_NAME, "ngb-dp-content"), timeout=30)
                last_restart_time = time.time()
                self.log("✅ Browser restarted successfully")
                
            # Find available date
            date_element = self.find_date()
            
            if date_element:
                empty_checks = 0
                try:
                    self.click_js(date_element)
                    self.log(f"✅ Clicked date {self.target_day}")
                    
                    if self.select_time_slot() and self.check_booking_success():
                        input("Booking complete! Press ENTER to exit...")
                        self.driver.quit()
                        return
                    else:
                        self.handle_failure()
                except Exception:
                    self.handle_failure()
            else:
                empty_checks += 1
                
            # Switch delivery type based on configured interval
            if (time.time() - last_switch_time > SWITCH_INTERVAL):
                self.switch_delivery_option()
                last_switch_time = time.time()
                empty_checks = 0
                
                # Check again immediately after switching
                date_element = self.find_date()
                if date_element:
                    try:
                        self.click_js(date_element)
                        self.log(f"✅ Clicked date {self.target_day} after switch")
                        
                        if self.select_time_slot() and self.check_booking_success():
                            input("Booking complete! Press ENTER to exit...")
                            self.driver.quit()
                            return
                        else:
                            self.handle_failure()
                    except Exception:
                        self.handle_failure()

if __name__ == "__main__":
    booker = PassportBooker()
    booker.run()