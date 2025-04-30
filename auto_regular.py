import time
import os
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

# Global variables
LOG_FILE = "booking_log.txt"
LOGGABLE_MESSAGES = [
    "=== Automation Log Start ===",
    "🌐 Opened",
    "📅 Calendar loaded",
    "✅ Date",
    "⏰ Selecting",
    "✅ Slot selected",
    "✅ Clicked",
    "✅ Summary page",
    "🛑 Browser closed",
    "BOOKING SUCCESSFUL",
    "🔄 Restarting",
]

NEGATIVE_MESSAGES = ["❌", "⚠️", "Error", "Failed", "Timeout"]

def log_message(message):
    """Log to both console and file with sound for negative messages"""
    print(message)

    if any(negative in message for negative in NEGATIVE_MESSAGES):
        os.system("afplay /System/Library/Sounds/Sosumi.aiff")

    if any(loggable in message for loggable in LOGGABLE_MESSAGES):
        with open(LOG_FILE, "a") as log_file:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            log_file.write(f"[{timestamp}] {message}\n")

def wait_for_element(locator, timeout=30):
    """Wait for an element with specified timeout"""
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(locator)
        )
    except TimeoutException:
        log_message(f"❌ Timeout: {locator}")
        return None

def click_element(locator, use_js=True, scroll=True):
    """Click an element with JavaScript for faster execution"""
    try:
        element = driver.find_element(*locator)
        if scroll:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", element
            )
        if use_js:
            driver.execute_script("arguments[0].click();", element)
        else:
            element.click()
        return True
    except Exception as e:
        log_message(f"❌ Click error: {locator}")
        return False

def clean_browser_cache():
    """Clear browser cache to prevent stale data"""
    try:
        driver.execute_script("window.localStorage.clear();")
        driver.execute_script("window.sessionStorage.clear();")
        log_message("🔄 Cache cleared")
    except Exception as e:
        log_message(f"⚠️ Cache clear failed")

def check_date_availability(target_day, delivery_option):
    """Check if the target date is available"""
    try:
        date_elements = driver.find_elements(
            By.XPATH, f"//div[@class='btn-light' and text()='{target_day}']"
        )
        for date_element in date_elements:
            if "disabled" not in date_element.get_attribute("class"):
                log_message(f"✅ Date {target_day} available under {delivery_option}!")
                return date_element
        return None
    except Exception as e:
        log_message(f"⚠️ Date check error")
        return None

def select_available_slot():
    """Select an available time slot using a smart randomized approach"""
    try:
        time_slots_container = wait_for_element(
            (By.CLASS_NAME, "vbeop-time-slots"), timeout=5
        )
        if not time_slots_container:
            log_message("❌ No time slots container")
            return False

        time_slot_labels = time_slots_container.find_elements(
            By.CLASS_NAME, "time-slot"
        )

        if not time_slot_labels:
            log_message("❌ No time slots")
            return False

        enabled_slots = []
        for slot in time_slot_labels:
            try:
                associated_input = driver.find_element(By.ID, slot.get_attribute("for"))
                if associated_input.is_enabled():
                    enabled_slots.append((slot, slot.text))
            except:
                continue

        if not enabled_slots:
            log_message("⚠️ No enabled slots found")
            return False

        enabled_slots.sort(key=lambda x: x[1])

        import random

        if random.random() < 0.6:
            selected_slot, slot_time = random.choice(enabled_slots)
            log_message(f"🎲 Randomly selected slot: {slot_time}")
        else:
            first_half = enabled_slots[: max(1, len(enabled_slots) // 2)]
            selected_slot, slot_time = random.choice(first_half)
            log_message(f"🎯 Selected earlier slot: {slot_time}")

        driver.execute_script("arguments[0].click();", selected_slot)
        log_message(f"✅ Slot selected: {slot_time}")

        save_button = driver.find_element(
            By.XPATH, "//span[text()='Save and continue']"
        )
        driver.execute_script("arguments[0].click();", save_button)
        log_message("✅ Clicked 'Save and Continue'")
        return True

    except Exception as e:
        log_message(f"❌ Slot selection error: {str(e)}")
        return False

def switch_delivery_option(current_option):
    """Switch between delivery options"""
    delivery_types = {
        "Regular delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.REGULAR']",
        "Express delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.EXPRESS']",
    }

    alternate = (
        "Express delivery"
        if current_option == "Regular delivery"
        else "Regular delivery"
    )

    try:
        # Use JavaScript for faster switching
        switch_element = driver.find_element(By.XPATH, delivery_types[alternate])
        driver.execute_script("arguments[0].click();", switch_element)
        log_message(f"✅ Switched to '{alternate}'")
        return alternate
    except Exception as e:
        log_message(f"⚠️ Switch error")
        return current_option

def check_for_errors():
    """Check for error messages on the page"""
    error_message_container = driver.find_elements(By.CLASS_NAME, "error-messages")
    if error_message_container:
        log_message("❌ Error message detected")
        return True
    return False

def handle_failure_and_retry():
    """Handle failures by refreshing the page"""
    log_message("🔄 Refreshing page")
    os.system("afplay /System/Library/Sounds/Funk.aiff")
    driver.refresh()
    time.sleep(2)
    clean_browser_cache()

def restart_browser_session(url, run_folder, run_id):
    """Restart the browser to prevent degradation during long runs"""
    global driver

    log_message("🔄 Restarting browser")

    try:
        driver.save_screenshot(f"{run_folder}/before_restart_{int(time.time())}.png")

        cookies = driver.get_cookies()

        driver.quit()

        time.sleep(2)

        chrome_options = Options()
        chrome_options.binary_location = (
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
        )
        service = Service("/opt/homebrew/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)

        driver.get(url)

        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
            except:
                pass

        driver.refresh()

        log_message("✅ Browser restarted")

        wait_for_element((By.CLASS_NAME, "ngb-dp-content"), timeout=90)
        log_message("📅 Calendar loaded after restart")

        return True
    except Exception as e:
        log_message(f"❌ Restart error")

        try:
            chrome_options = Options()
            chrome_options.binary_location = (
                "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
            )
            service = Service("/opt/homebrew/bin/chromedriver")
            driver = webdriver.Chrome(service=service, options=chrome_options)

            driver.get(url)
            log_message("✅ New browser started")

            input("Login required after restart. Press ENTER after login...")

            wait_for_element((By.CLASS_NAME, "ngb-dp-content"), timeout=90)
            log_message("📅 Calendar loaded after login")

            return True
        except Exception as e2:
            log_message(f"❌ Critical restart error")
            return False

def check_browser_health():
    """Check browser health by measuring response time"""
    try:
        start_time = time.time()
        driver.execute_script("return document.readyState")
        response_time = time.time() - start_time

        if response_time > 1.0:
            log_message(f"⚠️ Browser response slow: {response_time:.2f}s")
            return False
        return True
    except:
        log_message("⚠️ Health check failed")
        return False

def setup_date_watcher(target_day):
    """Set up a JavaScript MutationObserver to watch for date availability"""
    js_code = f"""
    window.dateDetected = false;
    window.targetDay = "{target_day}";
    
    // Create a MutationObserver to watch for DOM changes
    const observer = new MutationObserver(function(mutations) {{
        mutations.forEach(function(mutation) {{
            if (mutation.type === 'childList' || mutation.type === 'attributes') {{
                // Look for date elements that become enabled
                const dateElements = document.querySelectorAll('div.btn-light');
                dateElements.forEach(function(element) {{
                    if (element.textContent.trim() === window.targetDay && 
                        !element.classList.contains('disabled')) {{
                        window.dateDetected = true;
                        window.dateElement = element;
                        console.log("Date detected by observer!");
                    }}
                }});
            }}
        }});
    }});
    
    // Start observing the calendar container
    const calendarContainer = document.querySelector('.ngb-dp-content');
    if (calendarContainer) {{
        observer.observe(calendarContainer, {{ 
            childList: true, 
            subtree: true, 
            attributes: true,
            attributeFilter: ['class'] 
        }});
        console.log("Date observer started");
        return true;
    }}
    return false;
    """
    try:
        result = driver.execute_script(js_code)
        if result:
            log_message("✅ Date watcher set up")
        return result
    except Exception as e:
        log_message(f"❌ Error setting up date watcher")
        return False

def check_date_watcher():
    """Check if the JavaScript date watcher has detected a date"""
    try:
        detected = driver.execute_script("return window.dateDetected === true;")
        if detected:
            element = driver.execute_script("return window.dateElement;")
            log_message("🔍 Date detected by watcher!")
            return element
        return None
    except:
        return None

def rapid_date_check(target_day, max_attempts=5):
    """Perform rapid consecutive checks for date availability"""
    for _ in range(max_attempts):
        try:
            # Direct, minimal DOM query for faster execution
            js_code = f"""
            const dateElements = document.querySelectorAll('div.btn-light');
            for (let i = 0; i < dateElements.length; i++) {{
                const element = dateElements[i];
                if (element.textContent.trim() === "{target_day}" && 
                    !element.classList.contains('disabled')) {{
                    return element;
                }}
            }}
            return null;
            """
            element = driver.execute_script(js_code)
            if element:
                log_message(f"✅ Date {target_day} found with rapid check!")
                return element
        except:
            pass
        # Very short sleep to prevent CPU overload
        time.sleep(0.05)
    return None

def preload_calendar_data():
    """Preload calendar data to reduce latency when dates are released"""
    js_code = """
    // Preemptively fetch calendar data
    try {
        const today = new Date();
        const year = today.getFullYear();
        const month = today.getMonth();
        
        // Create a fetch request to preload calendar data
        fetch(`https://www.epassport.gov.bd/api/calendar/dates?year=${year}&month=${month}`, {
            method: 'GET',
            credentials: 'include'
        }).then(response => {
            console.log("Calendar data preloaded");
            return true;
        }).catch(error => {
            console.error("Failed to preload calendar data");
            return false;
        });
        return true;
    } catch (e) {
        return false;
    }
    """
    try:
        driver.execute_script(js_code)
        log_message("🔄 Preloaded calendar data")
    except:
        pass

def main_task():
    global driver

    import random

    run_id = random.randint(1000, 9999)
    run_folder = f"run_{run_id}"
    os.makedirs(run_folder, exist_ok=True)

    global LOG_FILE
    LOG_FILE = os.path.join(run_folder, f"log-{run_id}.txt")
    with open(LOG_FILE, "w") as log_file:
        log_file.write("=== Automation Log Start ===\n")

    chrome_options = Options()
    chrome_options.binary_location = (
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
    )
    service = Service("/opt/homebrew/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options)

    target_date = datetime.now()
    target_day = target_date.day

    booking_url = "https://www.epassport.gov.bd/authorization/login"
    driver.get(booking_url)
    log_message("🌐 Opened login page")
    input("Press ENTER after login...")

    wait_for_element((By.CLASS_NAME, "ngb-dp-content"), timeout=90)
    log_message("📅 Calendar loaded")
    
    current_delivery = "Regular delivery"
    click_element(
        (
            By.XPATH,
            "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.REGULAR']",
        )
    )

    last_switch_time = time.time()
    switch_interval = 8
    consecutive_empty_checks = 0
    max_empty_checks = 3

    session_start_time = time.time()
    browser_restart_interval = 60 * 60
    last_health_check_time = time.time()
    health_check_interval = 5 * 60

    while True:
        current_time = time.time()
        session_duration = current_time - session_start_time

        if session_duration >= browser_restart_interval:
            if restart_browser_session(booking_url, run_folder, run_id):
                session_start_time = time.time()
                last_health_check_time = time.time()
                current_delivery = "Regular delivery"
                click_element(
                    (
                        By.XPATH,
                        "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.REGULAR']",
                    )
                )
            else:
                log_message("❌ Failed to restart browser")
                break

        if current_time - last_health_check_time >= health_check_interval:
            if not check_browser_health():
                log_message("⚠️ Browser health check failed")
                if restart_browser_session(booking_url, run_folder, run_id):
                    session_start_time = time.time()
                    last_health_check_time = time.time()
                    current_delivery = "Regular delivery"
                    click_element(
                        (
                            By.XPATH,
                            "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.REGULAR']",
                        )
                    )
                else:
                    log_message("❌ Failed to restart after health check")
                    break
            else:
                last_health_check_time = current_time
                log_message("✅ Health check passed")

        date_element = check_date_availability(target_day, current_delivery)

        if date_element:
            consecutive_empty_checks = 0

            try:

                driver.execute_script("arguments[0].click();", date_element)
                log_message(f"✅ Date {target_day} clicked under {current_delivery}")

                if select_available_slot():
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.url_matches(
                                r"https://www.epassport.gov.bd/applications/application-form/.*/summary"
                            )
                        )
                        log_message("✅ BOOKING SUCCESSFUL!")
                        driver.save_screenshot(f"{run_folder}/success-{run_id}.png")
                        os.system("afplay /System/Library/Sounds/Glass.aiff")
                        os.system("afplay /System/Library/Sounds/Glass.aiff")
                        os.system("afplay /System/Library/Sounds/Glass.aiff")

                        time.sleep(2)

                        driver.get("https://www.epassport.gov.bd/home/account/edit")
                        log_message("✅ Navigated to account edit page")

                        input("Booking successful! Press ENTER to close the browser...")
                        driver.quit()
                        log_message("🛑 Browser closed")
                        break  # Success!
                    except:
                        log_message("⚠️ Slot selected but summary page not loaded")
                        if check_for_errors():
                            handle_failure_and_retry()
                else:
                    log_message("⚠️ Failed to select time slot")
                    handle_failure_and_retry()
            except Exception as e:
                log_message(f"⚠️ Error after date found")
                handle_failure_and_retry()
        else:
            consecutive_empty_checks += 1

        current_time = time.time()
        time_since_switch = current_time - last_switch_time

        if time_since_switch >= switch_interval and (
            consecutive_empty_checks >= max_empty_checks
            or time_since_switch >= switch_interval * 2
        ):

            current_delivery = switch_delivery_option(current_delivery)
            last_switch_time = current_time
            consecutive_empty_checks = 0

            date_element = check_date_availability(target_day, current_delivery)
            if date_element:
                try:
                    driver.execute_script("arguments[0].click();", date_element)
                    log_message(
                        f"✅ Date {target_day} clicked under {current_delivery} (after switch)"
                    )

                    if select_available_slot():
                        try:
                            WebDriverWait(driver, 10).until(
                                EC.url_matches(
                                    r"https://www.epassport.gov.bd/applications/application-form/.*/summary"
                                )
                            )
                            log_message("✅ BOOKING SUCCESSFUL!")
                            driver.save_screenshot(f"{run_folder}/success-{run_id}.png")
                            os.system("afplay /System/Library/Sounds/Glass.aiff")
                            os.system("afplay /System/Library/Sounds/Glass.aiff")
                            os.system("afplay /System/Library/Sounds/Glass.aiff")

                            time.sleep(2)

                            driver.get("https://www.epassport.gov.bd/home/account/edit")
                            log_message("✅ Navigated to account edit page")

                            input(
                                "Booking successful! Press ENTER to close the browser..."
                            )
                            driver.quit()
                            log_message("🛑 Browser closed")
                            break
                        except:
                            log_message("⚠️ Slot selected but summary page not loaded")
                            if check_for_errors():
                                handle_failure_and_retry()
                except Exception as e:
                    log_message(f"⚠️ Error after date found (post-switch)")
                    handle_failure_and_retry()

    if (
        driver.current_url
        and "summary" not in driver.current_url
        and "account/edit" not in driver.current_url
    ):
        input("Press ENTER to close the browser...")
        driver.quit()
        log_message("🛑 Browser closed")


if __name__ == "__main__":
    main_task()

"""
buessnessman13@gmail.com
onlinaservice6@gmail.com
alatif21@outlook.com
highser7@gmail.com
sahadat.mso@gmail.com
"""