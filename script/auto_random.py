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

chrome_options = Options()
chrome_options.binary_location = (
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
)
service = Service("/opt/homebrew/bin/chromedriver")
driver = webdriver.Chrome(service=service, options=chrome_options)

LOG_FILE = "log.txt"

LOGGABLE_MESSAGES = [
    "=== Automation Log Start ===",
    "🌐 Opened the login page",
    "📅 Calendar loaded successfully.",
    "✅ Date",
    "⏰ Selecting time slot:",
    "✅ Slot selected successfully under",
    "✅ Clicked 'Save and Continue' button.",
    "✅ Summary page loaded successfully.",
    "🛑 Browser closed successfully.",
]

def log_message(message):
    print(message)

    if any(loggable in message for loggable in LOGGABLE_MESSAGES):
        with open(LOG_FILE, "a") as log_file:
            log_file.write(f"{message}\n")

def wait_for_element(locator, timeout=30):
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(locator)
        )
    except TimeoutException:
        log_message(f"❌ Timeout waiting for element: {locator}")
        raise

def click_element(locator, scroll=True):
    try:
        element = driver.find_element(*locator)
        if scroll:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", element
            )
        element.click()
        return True
    except Exception as e:
        log_message(f"❌ Error clicking element: {locator}, {e}")
        return False

def clean_browser_cache():
    try:
        driver.execute_script("window.localStorage.clear();")
        driver.execute_script("window.sessionStorage.clear();")
        log_message("🔄 Browser cache cleared.")
    except Exception as e:
        log_message(f"⚠️ Failed to clear browser cache: {e}")

def alternate_delivery_button(selected_delivery, target_day):
    delivery_types = {
        "Regular delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.REGULAR']",
        "Express delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.EXPRESS']",
    }
    alternate_delivery = (
        "Express delivery" if selected_delivery == "Regular delivery" else "Regular delivery"
    )

    # Switch to alternate delivery option
    if click_element((By.XPATH, delivery_types[alternate_delivery])):
        log_message(f"✅ Switched to '{alternate_delivery}'")
        if wait_for_element((By.CLASS_NAME, "ngb-dp-content"), timeout=5):
            try:
                date_available = driver.find_elements(
                    By.XPATH, f"//div[@class='btn-light' and text()='{target_day}']"
                )
                if date_available and "disabled" not in date_available[0].get_attribute("class"):
                    log_message(f"✅ Target date detected in '{alternate_delivery}'. Selecting immediately...")
                    date_available[0].click()
                    return alternate_delivery  # Switch and proceed with the alternate option
            except Exception as e:
                log_message(f"⚠️ Polling inactive option failed: {e}")
                # Retry on failure or return to original
                click_element((By.XPATH, delivery_types[selected_delivery]))
                return selected_delivery
    else:
        log_message(f"⚠️ Failed to switch to '{alternate_delivery}'. Retrying current delivery...")

    # Return to original delivery option if no date is found or errors occur
    click_element((By.XPATH, delivery_types[selected_delivery]))
    log_message(f"✅ Staying on '{selected_delivery}' after checking '{alternate_delivery}'.")
    return selected_delivery

def handle_failure_and_retry():
    log_message("🔄 Refreshing the page to retry...")
    os.system("afplay /System/Library/Sounds/Funk.aiff")
    driver.refresh()
    time.sleep(3)
    clean_browser_cache()

def check_for_errors():
    error_message_container = driver.find_elements(By.CLASS_NAME, "error-messages")
    if error_message_container:
        log_message("❌ Error message detected on the page. Refreshing...")
        handle_failure_and_retry()
        return True
    return False

def main_task():
    import random
    global driver  # Ensure this is declared at the top
    global run_id
    run_id = random.randint(1, 100)
    run_folder = f"run_{run_id}"
    os.makedirs(run_folder, exist_ok=True)

    global LOG_FILE
    LOG_FILE = os.path.join(run_folder, f"log-{run_id}.txt")
    with open(LOG_FILE, "w") as log_file:
        log_file.write("=== Automation Log Start ===\n")

    # target_date_str = "10/08/25"
    target_date_str = datetime.now().strftime("%d/%m/%y")
    target_date = datetime.strptime(target_date_str, "%d/%m/%y")
    target_day = target_date.day

    driver.get("https://www.epassport.gov.bd/authorization/login")
    log_message("🌐 Opened the login page")
    input("Press ENTER to continue...")

    wait_for_element((By.CLASS_NAME, "ngb-dp-content"), timeout=90)
    log_message("📅 Calendar loaded successfully.")

    selected_delivery = "Regular delivery"
    last_switch_time = time.time()
    switch_interval = 7  # Wait for 7 seconds before switching

    while True:
        if run_id % 20 == 0:
            log_message("🔄 Restarting browser session to prevent degradation...")
            driver.quit()
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.get("https://www.epassport.gov.bd/authorization/login")
            log_message("🌐 Browser session restarted successfully.")
            input("Press ENTER to continue...")

        date_clicked = False
        try:
            # Wait for the target date to be present and clickable
            date_element = WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.XPATH, f"//div[@class='btn-light' and text()='{target_day}']"))
            )
            if "disabled" not in date_element.get_attribute("class"):
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", date_element)
                    date_element.click()
                    if check_for_errors():
                        continue
                    log_message(f"✅ Date {target_day} selected under '{selected_delivery}'.")
                    date_clicked = True
                except Exception as e:
                    log_message(f"❌ Error clicking date element: {e}")
                    if time.time() - last_switch_time >= switch_interval:
                        selected_delivery = alternate_delivery_button(selected_delivery, target_day)
                        last_switch_time = time.time()
                    continue
            else:
                log_message("❌ Target date is disabled. Retrying dynamically...")
                if time.time() - last_switch_time >= switch_interval:
                    selected_delivery = alternate_delivery_button(selected_delivery, target_day)
                    last_switch_time = time.time()
                continue
        except TimeoutException:
            log_message("❌ Target date not found. Retrying dynamically...")
            if time.time() - last_switch_time >= switch_interval:
                selected_delivery = alternate_delivery_button(selected_delivery, target_day)
                last_switch_time = time.time()
            continue

        try:
            log_message("⏳ Waiting for time slots...")
            time_slots_container = wait_for_element((By.CLASS_NAME, "vbeop-time-slots"))
            time_slot_labels = time_slots_container.find_elements(By.CLASS_NAME, "time-slot")
            slot_selected = False
            import random
            if time_slot_labels:
                random_slot = random.choice(time_slot_labels)  # Pick a random slot
                associated_input = driver.find_element(By.ID, random_slot.get_attribute("for"))
                if associated_input.is_enabled():
                    log_message(f"⏰ Randomly selecting time slot: {random_slot.text}")
                    try:
                        random_slot.click()
                        log_message(f"✅ Slot selected successfully under '{selected_delivery}' with time slot '{random_slot.text}'.")
                        if check_for_errors():  # Handle server-side submission error dynamically
                            log_message("❌ Submission error detected. Retrying another slot...")
                            continue  # Retry dynamically without refreshing the page
                        slot_selected = True
                    except Exception as e:
                        log_message(f"❌ Error clicking random time slot: {e}")
                        slot_selected = False
                else:
                    log_message("❌ Selected time slot is not clickable. Retrying...")
                    slot_selected = False
                if not slot_selected:
                    sorted_slots = sorted(time_slot_labels, key=lambda slot: slot.text)  # Sort slots by time for prioritized selection
                    for slot in sorted_slots:
                        associated_input = driver.find_element(By.ID, slot.get_attribute("for"))
                        if associated_input.is_enabled():
                            log_message(f"⏰ Attempting to select prioritized slot: {slot.text}")
                            try:
                                slot.click()
                                log_message(f"✅ Slot '{slot.text}' selected successfully under '{selected_delivery}'.")
                                if check_for_errors():
                                    continue
                                break  # Exit loop after successful slot selection
                            except Exception as e:
                                log_message(f"❌ Failed to click slot '{slot.text}': {e}")
                                continue
            else:
                log_message("❌ No time slots available. Refreshing...")
                handle_failure_and_retry()
                date_clicked = False
                continue
        except Exception as e:
            log_message(f"❌ Error selecting slot: {e}. Refreshing...")
            handle_failure_and_retry()
            date_clicked = False
            continue

        try:
            if not click_element((By.XPATH, "//span[text()='Save and continue']")):
                raise Exception("Failed to click 'Save and continue'")
            log_message("✅ Clicked 'Save and Continue' button.")
            if check_for_errors():
                date_clicked = False
                continue
            WebDriverWait(driver, 30).until(
                EC.url_matches(r"https://www.epassport.gov.bd/applications/application-form/.*/summary")
            )
            log_message("✅ Summary page loaded successfully.")
            driver.save_screenshot(f"{run_folder}/schedule-{run_id}.png")
            os.system("afplay /System/Library/Sounds/Glass.aiff")
            os.system("afplay /System/Library/Sounds/Glass.aiff")
            os.system("afplay /System/Library/Sounds/Glass.aiff")
        except Exception as e:
            log_message(f"❌ Submission failed: {e}. Refreshing...")
            handle_failure_and_retry()
            date_clicked = False
            continue

        if date_clicked is False:
            log_message("❌ Error detected after date selection. Refreshing page...")
            handle_failure_and_retry()
            continue

        input("Press ENTER to close the browser...")
        driver.quit()
        log_message("🛑 Browser closed successfully.")
        break

if __name__ == "__main__":
    main_task()