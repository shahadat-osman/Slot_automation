import logging
import subprocess
import sys
import threading
import time
from datetime import datetime
from threading import Lock
import random

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

# Import added functions from notifications.py
from notifications import extract_info, send_whatsapp_message

# Configuration constants
CONFIG = {
    "BRAVE_PATH": "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "CHROMEDRIVER_PATH": "/opt/homebrew/bin/chromedriver",
    "DATE_ELEMENT_TIMEOUT": 2,
    "TARGET_DATE_STR": datetime.now().strftime("%d/%m/%y"),
    "DELIVERY_TYPES": {
        "Regular delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.REGULAR']",
        "Express delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.EXPRESS']",
    },
    "SOUND_PATHS": {
        "refresh": "/System/Library/Sounds/Funk.aiff",
        "success": "/System/Library/Sounds/Glass.aiff",
    },
}

# Setup logger
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

chrome_options = Options()
chrome_options.binary_location = CONFIG["BRAVE_PATH"]


def create_driver():
    try:
        return webdriver.Chrome(
            service=Service(CONFIG["CHROMEDRIVER_PATH"]), options=chrome_options
        )
    except Exception as e:
        log_message("Driver creation failed", level="error")
        raise


def log_message(message, level="info"):
    if level == "info":
        logger.info(message)
    elif level == "error":
        logger.error(message)
    elif level == "warning":
        logger.warning(message)
    else:
        logger.info(message)


def wait_for_element(driver, locator, timeout=30):
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(locator)
        )
    except TimeoutException:
        log_message("Element wait timeout", level="error")
        raise


def click_element(driver, locator, scroll=True):
    try:
        element = driver.find_element(*locator)
        if scroll:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", element
            )
        element.click()
        return True
    except Exception as e:
        log_message("Element click failed", level="error")
        return False


delivery_switch_count = 0
delivery_switch_lock = Lock()


def alternate_delivery_button(driver, selected_delivery):
    """
    Alternates the delivery type and logs the switch.

    Args:
        driver: The Selenium WebDriver instance.
        selected_delivery (str): Current delivery option.

    Returns:
        str: The new delivery option.
    """
    global delivery_switch_count
    delivery_types = CONFIG["DELIVERY_TYPES"]
    next_delivery = (
        "Express delivery" if selected_delivery == "Regular delivery" else "Regular delivery"
    )
    switched = click_element(driver, (By.XPATH, delivery_types[next_delivery]))
    if switched:
        with delivery_switch_lock:  # Synchronize access to the counter and logging
            delivery_switch_count += 1
            log_message(f"Delivery type switched {delivery_switch_count}")
        try:
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, delivery_types[next_delivery]))
            )
        except TimeoutException:
            log_message("Timeout after switching delivery", level="warning")
        return next_delivery
    return selected_delivery


def handle_failure_and_retry(driver):
    log_message("Refreshing page to retry")
    try:
        subprocess.run(["afplay", CONFIG["SOUND_PATHS"]["refresh"]], check=False)
    except Exception as e:
        log_message("Refresh sound failed", level="warning")
    driver.refresh()
    time.sleep(3)


def is_session_active(driver):
    try:
        driver.execute_script("return document.readyState")
        return True
    except Exception:
        return False


def cleanup_drivers(drivers):
    for driver in drivers:
        try:
            if is_session_active(driver):
                log_message(f"Closing driver: {driver.session_id}")
                driver.quit()
        except Exception as e:
            log_message(f"Driver close failed: {e}", level="warning")


def handle_error_and_exit(drivers, message):
    session_terminated_event.set()
    log_message(message, level="error")
    cleanup_drivers(drivers)
    sys.exit(0)


def check_for_errors(driver):
    error_message_containers = driver.find_elements(By.CLASS_NAME, "error-messages")
    if error_message_containers:
        for container in error_message_containers:
            text = container.text.strip()
            if text:
                log_message("Page error detected", level="error")
        handle_failure_and_retry(driver)
        return True
    return False


def select_date(driver, target_day, selected_delivery):
    try:
        date_element = WebDriverWait(driver, CONFIG["DATE_ELEMENT_TIMEOUT"]).until(
            EC.presence_of_element_located(
                (By.XPATH, f"//div[@class='btn-light' and text()='{target_day}']")
            )
        )
        if "disabled" not in date_element.get_attribute("class"):
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", date_element
                )
                date_element.click()
                if check_for_errors(driver):
                    session_terminated_event.set()
                    handle_error_and_exit([driver], "Error after clicking date")
                log_message("Date selected")
                return True, selected_delivery
            except Exception as e:
                log_message("Date click failed", level="error")
                selected_delivery = alternate_delivery_button(driver, selected_delivery)
                return False, selected_delivery
        else:
            log_message("Target date disabled, retrying")
            selected_delivery = alternate_delivery_button(driver, selected_delivery)
            return False, selected_delivery
    except TimeoutException:
        selected_delivery = alternate_delivery_button(driver, selected_delivery)
        return False, selected_delivery


def automate_booking(driver, initial_delivery, drivers):
    target_date = datetime.strptime(CONFIG["TARGET_DATE_STR"], "%d/%m/%y")
    target_day = target_date.day

    selected_delivery = initial_delivery

    wait_for_element(driver, (By.CLASS_NAME, "ngb-dp-content"), timeout=90)
    log_message("Calendar loaded")

    while True:
        date_clicked = False

        date_clicked, selected_delivery = select_date(
            driver, target_day, selected_delivery
        )
        if not date_clicked:
            continue

        try:
            log_message("Waiting for slots")
            time_slots_container = wait_for_element(
                driver, (By.CLASS_NAME, "vbeop-time-slots")
            )
            time_slot_labels = time_slots_container.find_elements(
                By.CLASS_NAME, "time-slot"
            )
            slot_selected = False

            random.shuffle(time_slot_labels)
            for time_slot in time_slot_labels:
                try:
                    associated_input = driver.find_element(
                        By.ID, time_slot.get_attribute("for")
                    )
                except NoSuchElementException:
                    log_message("No input for slot", level="warning")
                    continue
                if associated_input.is_enabled():
                    log_message("Selecting time slot")
                    try:
                        time_slot.click()
                        log_message("Slot selected")
                        if check_for_errors(driver):
                            date_clicked = False
                            slot_selected = False
                            break
                        slot_selected = True
                        break
                    except Exception as e:
                        log_message("Slot click failed", level="error")
                        continue

            if not slot_selected:
                session_terminated_event.set()
                handle_error_and_exit([driver], "No slots available")
        except Exception as e:
            log_message("Slot selection failed", level="error")
            handle_failure_and_retry(driver)
            date_clicked = False
            continue

        try:
            if not click_element(
                driver, (By.XPATH, "//span[text()='Save and continue']")
            ):
                raise Exception("Failed to click 'Save and continue'")
            log_message("Clicked Save and Continue")
            current_time = datetime.now().strftime("%H:%M:%S")
            driver.save_screenshot(f"{current_time}-slot.png")
            try:
                subprocess.run(
                    ["afplay", CONFIG["SOUND_PATHS"]["success"]], check=False
                )
            except Exception as e:
                log_message("Success sound failed", level="warning")
            if check_for_errors(driver):
                session_terminated_event.set()
                handle_error_and_exit([driver], "Error after Save and Continue")
            WebDriverWait(driver, 30).until(
                EC.url_matches(
                    r"https://www.epassport.gov.bd/applications/application-form/.*/summary"
                )
            )
            log_message("Summary page loaded")
            time.sleep(2)

            recipients = ["+8801757000310"]  #   , "+96878289115", "+96894562190"

            try:
                name, appointment_time, email = extract_info(driver)
                send_whatsapp_message(name, appointment_time, email, recipients)
                log_message("WhatsApp messages sent successfully. Exiting...")
                session_terminated_event.set()
                return
            except Exception as e:
                log_message(f"Error during WhatsApp notification: {e}", level="error")

        except Exception as e:
            log_message("Submission failed", level="error")
            handle_failure_and_retry(driver)
            date_clicked = False
            continue

        if not date_clicked:
            log_message("Error after date selection, refreshing")
            handle_failure_and_retry(driver)
            continue

        # cleanup_drivers([driver])
        # sys.exit(0)


from threading import Event

shutdown_event = Event()
session_terminated_event = Event()

def run_automate_booking(driver, delivery, drivers):
    try:
        if not session_terminated_event.is_set():
            automate_booking(driver, delivery, drivers)
    except Exception as e:
        session_terminated_event.set()
        log_message(f"Thread exception: {e}", level="error")
    finally:
        log_message(f"Thread for delivery '{delivery}' completed.")


def main():
    drivers = []
    try:
        driver1 = create_driver()
        driver2 = create_driver()
        drivers.extend([driver1, driver2])
    except Exception:
        log_message("Driver launch failed", level="error")
        cleanup_drivers(drivers)
        return

    try:
        driver1.get("https://www.epassport.gov.bd/authorization/login")
        driver2.get("https://www.epassport.gov.bd/authorization/login")
        log_message("Browsers opened. Login manually.")

        input("Press ENTER after completing login in both browsers...")

        thread1 = threading.Thread(
            target=run_automate_booking, args=(driver1, "Regular delivery", drivers)
        )
        thread2 = threading.Thread(
            target=run_automate_booking, args=(driver2, "Express delivery", drivers)
        )

        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()

        log_message("All threads completed.")

    except Exception as e:
        log_message(f"Unexpected error: {e}", level="error")
    finally:
        cleanup_drivers(drivers)
        log_message("Drivers cleaned up. Exiting...")
        return


if __name__ == "__main__":
    main()
