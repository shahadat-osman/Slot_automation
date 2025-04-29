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

def wait_for_element(locator, timeout=10):
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
        driver.execute_script("arguments[0].click();", element)
        return True
    except Exception as e:
        log_message(f"❌ Error clicking element: {locator}, {e}")
        return False

def alternate_delivery_button(selected_delivery):
    delivery_types = {
        "Regular delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.REGULAR']",
        "Express delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.EXPRESS']",
    }
    next_delivery = (
        "Express delivery"
        if selected_delivery == "Regular delivery"
        else "Regular delivery"
    )
    if click_element((By.XPATH, delivery_types[next_delivery])):
        log_message(f"✅ Switched to '{next_delivery}'")
        try:
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, delivery_types[next_delivery]))
            )
        except TimeoutException:
            log_message(f"⚠️ Timeout waiting after switching to '{next_delivery}'.")
        return next_delivery
    else:
        log_message(f"⚠️ Failed to switch to '{next_delivery}'.")
        return selected_delivery

def handle_failure_and_retry():
    log_message("🔄 Refreshing the page to retry...")
    os.system("afplay /System/Library/Sounds/Funk.aiff")
    driver.refresh()
    time.sleep(2)

def check_for_errors():
    error_message_container = driver.find_elements(By.CLASS_NAME, "error-messages")
    if error_message_container:
        log_message("❌ Error message detected on the page. Refreshing...")
        handle_failure_and_retry()
        return True
    return False

def main_task():
    import random
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
    switch_interval = 4  # seconds

    while True:
        if time.time() - last_switch_time > switch_interval:
            selected_delivery = alternate_delivery_button(selected_delivery)
            last_switch_time = time.time()

        date_clicked = False
        try:
            # Wait for the target date to be present and clickable
            date_element = WebDriverWait(driver, 7).until(
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
                    selected_delivery = alternate_delivery_button(selected_delivery)
                    continue
            else:
                log_message("❌ Target date is disabled. Retrying dynamically...")
                selected_delivery = alternate_delivery_button(selected_delivery)
                continue
        except TimeoutException:
            log_message("❌ Target date not found. Retrying dynamically...")
            selected_delivery = alternate_delivery_button(selected_delivery)
            continue

        try:
            log_message("⏳ Waiting for time slots...")
            time_slots_container = wait_for_element((By.CLASS_NAME, "vbeop-time-slots"))
            time_slot_labels = time_slots_container.find_elements(By.CLASS_NAME, "time-slot")
            slot_selected = False
            for time_slot in reversed(time_slot_labels):
                associated_input = driver.find_element(By.ID, time_slot.get_attribute("for"))
                if associated_input.is_enabled():
                    log_message(f"⏰ Selecting time slot: {time_slot.text}")
                    try:
                        time_slot.click()
                        log_message(f"✅ Slot selected successfully under '{selected_delivery}' with time slot '{time_slot.text}'.")
                        if check_for_errors():
                            date_clicked = False
                            slot_selected = False
                            break
                        slot_selected = True
                        break
                    except Exception as e:
                        log_message(f"❌ Error clicking time slot: {e}")
                        continue
            if not slot_selected:
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