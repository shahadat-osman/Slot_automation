import time
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from random import choice
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementNotInteractableException,
    ElementClickInterceptedException,
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import threading

BRAVE_PATH = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
CHROMEDRIVER_PATH = "/opt/homebrew/bin/chromedriver"
DATE_ELEMENT_TIMEOUT = 2

chrome_options = Options()
chrome_options.binary_location = BRAVE_PATH


def create_driver():
    return webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=chrome_options)


def log_message(message):
    print(message)


def wait_for_element(driver, locator, timeout=30):
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(locator)
        )
    except TimeoutException:
        log_message(f"❌ Timeout waiting for element: {locator}")
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
        log_message(f"❌ Error clicking element: {locator}, {e}")
        return False


def alternate_delivery_button(driver, selected_delivery):
    delivery_types = {
        "Regular delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.REGULAR']",
        "Express delivery": "//label[@for='delivery-type-idRegistrationForm.DeliveryOptions.DeliveryTypeLabels.EXPRESS']",
    }
    next_delivery = (
        "Express delivery"
        if selected_delivery == "Regular delivery"
        else "Regular delivery"
    )
    if click_element(driver, (By.XPATH, delivery_types[next_delivery])):
        if selected_delivery == "Regular delivery":
            log_message("✅ Switched successfully.")
        try:
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, delivery_types[next_delivery]))
            )
        except TimeoutException:
            log_message(f"⚠️ Timeout waiting after switching to '{next_delivery}'.")
        return next_delivery
    else:
        # log_message("⚠️ Failed to switch option.")
        return selected_delivery


def handle_failure_and_retry(driver):
    log_message("🔄 Refreshing the page to retry...")
    os.system("afplay /System/Library/Sounds/Funk.aiff")
    driver.refresh()
    time.sleep(3)


def check_for_errors(driver):
    error_message_container = driver.find_elements(By.CLASS_NAME, "error-messages")
    if error_message_container:
        log_message("❌ Error message detected on the page. Refreshing...")
        handle_failure_and_retry(driver)
        return True
    return False


def automate_booking(driver, initial_delivery):
    # target_date_str = "05/09/25"
    target_date_str = datetime.now().strftime("%d/%m/%y")
    target_date = datetime.strptime(target_date_str, "%d/%m/%y")
    target_day = target_date.day

    selected_delivery = initial_delivery

    wait_for_element(driver, (By.CLASS_NAME, "ngb-dp-content"), timeout=90)
    log_message(f"📅 Calendar loaded successfully for {initial_delivery}.")

    while True:
        date_clicked = False
        try:
            date_element = WebDriverWait(driver, DATE_ELEMENT_TIMEOUT).until(
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
                        continue
                    log_message(
                        f"✅ Date {target_day} selected under '{selected_delivery}'."
                    )
                    date_clicked = True
                except Exception as e:
                    log_message(f"❌ Error clicking date element: {e}")
                    selected_delivery = alternate_delivery_button(
                        driver, selected_delivery
                    )
                    continue
            else:
                log_message("❌ Target date is disabled. Retrying dynamically...")
                selected_delivery = alternate_delivery_button(driver, selected_delivery)
                continue
        except TimeoutException:
            selected_delivery = alternate_delivery_button(driver, selected_delivery)
            continue

        try:
            log_message("⏳ Waiting for slots...")
            time_slots_container = wait_for_element(
                driver, (By.CLASS_NAME, "vbeop-time-slots")
            )
            time_slot_labels = time_slots_container.find_elements(
                By.CLASS_NAME, "time-slot"
            )
            slot_selected = False

            while time_slot_labels:
                time_slot = choice(time_slot_labels)
                associated_input = driver.find_element(
                    By.ID, time_slot.get_attribute("for")
                )
                if associated_input.is_enabled():
                    log_message(f"⏰ Selecting time slot: {time_slot.text}")
                    try:
                        time_slot.click()
                        log_message(
                            f"✅ Slot selected under '{selected_delivery}' with time slot '{time_slot.text}'."
                        )
                        if check_for_errors(driver):
                            date_clicked = False
                            slot_selected = False
                            break
                        slot_selected = True
                        break
                    except Exception as e:
                        log_message(f"❌ Error clicking time slot: {e}")
                        continue

            if not slot_selected:
                log_message("❌ No slots available. Refreshing...")
                handle_failure_and_retry(driver)
                date_clicked = False
                continue
        except Exception as e:
            log_message(f"❌ Error selecting slot: {e}. Refreshing...")
            handle_failure_and_retry(driver)
            date_clicked = False
            continue

        try:
            if not click_element(
                driver, (By.XPATH, "//span[text()='Save and continue']")
            ):
                raise Exception("Failed to click 'Save and continue'")
            log_message("✅ Clicked 'Save and Continue' button.")
            driver.save_screenshot("slot.png")
            os.system("afplay /System/Library/Sounds/Glass.aiff")
            if check_for_errors(driver):
                date_clicked = False
                continue
            WebDriverWait(driver, 30).until(
                EC.url_matches(
                    r"https://www.epassport.gov.bd/applications/application-form/.*/summary"
                )
            )
            log_message("✅ Summary page loaded successfully.")
            driver.save_screenshot("summary.png")
            os.system("afplay /System/Library/Sounds/Glass.aiff")
        except Exception as e:
            log_message(f"❌ Submission failed: {e}. Refreshing...")
            handle_failure_and_retry(driver)
            date_clicked = False
            continue

        if not date_clicked:
            log_message("❌ Error detected after date selection. Refreshing page...")
            handle_failure_and_retry(driver)
            continue

        input("Press ENTER to close all browsers...")
        driver.quit()
        os._exit(0)


def main():
    driver1 = create_driver()
    driver2 = create_driver()

    driver1.get("https://www.epassport.gov.bd/authorization/login")
    driver2.get("https://www.epassport.gov.bd/authorization/login")
    log_message("🌐 Both browsers opened. Please login manually.")

    input("Press ENTER after completing login in both browsers...")

    thread1 = threading.Thread(
        target=automate_booking, args=(driver1, "Regular delivery")
    )
    thread2 = threading.Thread(
        target=automate_booking, args=(driver2, "Express delivery")
    )

    thread1.start()
    thread2.start()

    thread1.join()
    thread2.join()


if __name__ == "__main__":
    main()
