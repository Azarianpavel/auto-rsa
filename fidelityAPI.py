# Nelson Dane
# API to Interface with Fidelity
# Uses headless Selenium

import datetime
import os
import re
import traceback
from time import sleep

from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait

from helperAPI import (
    Brokerage,
    check_if_page_loaded,
    getDriver,
    printAndDiscord,
    stockOrder,
    type_slowly,
)


def fidelity_error(driver: webdriver, error: str):
    print(f"Fidelity Error: {error}")
    driver.save_screenshot(f"fidelity-error-{datetime.datetime.now()}.png")
    print(traceback.format_exc())


def javascript_get_classname(driver: webdriver, className) -> list:
    script = f"""
    var accounts = document.getElementsByClassName("{className}");
    var account_list = [];
    for (var i = 0; i < accounts.length; i++) {{
        account_list.push(accounts[i].textContent.trim());
    }}
    return account_list;
    """
    text = driver.execute_script(script)
    sleep(1)
    return text


def fidelity_init(FIDELITY_EXTERNAL=None, DOCKER=False):
    # Initialize .env file
    load_dotenv()
    # Import Fidelity account
    if not os.getenv("FIDELITY") and FIDELITY_EXTERNAL is None:
        print("Fidelity not found, skipping...")
        return None
    accounts = (
        os.environ["FIDELITY"].strip().split(",")
        if FIDELITY_EXTERNAL is None
        else FIDELITY_EXTERNAL.strip().split(",")
    )
    fidelity_obj = Brokerage("Fidelity")
    # Init webdriver
    for account in accounts:
        index = accounts.index(account) + 1
        name = f"Fidelity {index}"
        account = account.split(":")
        try:
            print("Logging in to Fidelity...")
            driver = getDriver(DOCKER)
            if driver is None:
                raise Exception("Error: Unable to get driver")
            # Log in to Fidelity account
            driver.get(
                "https://digital.fidelity.com/prgw/digital/login/full-page?AuthRedUrl=digital.fidelity.com/ftgw/digital/portfolio/summary"
            )
            # Wait for page load
            WebDriverWait(driver, 20).until(check_if_page_loaded)
            # Type in username and password and click login
            WebDriverWait(driver, 10).until(
                expected_conditions.element_to_be_clickable(
                    (By.CSS_SELECTOR, "#userId-input")
                )
            )
            username_field = driver.find_element(
                by=By.CSS_SELECTOR, value="#userId-input"
            )
            type_slowly(username_field, account[0])
            WebDriverWait(driver, 10).until(
                expected_conditions.element_to_be_clickable(
                    (By.CSS_SELECTOR, "#password")
                )
            )
            password_field = driver.find_element(by=By.CSS_SELECTOR, value="#password")
            type_slowly(password_field, account[1])
            driver.find_element(by=By.CSS_SELECTOR, value="#fs-login-button").click()
            WebDriverWait(driver, 10).until(check_if_page_loaded)
            sleep(3)
            # Wait for page to load to summary page
            if "summary" not in driver.current_url:
                if "errorpage" in driver.current_url.lower():
                    raise Exception(
                        f"{name}: Login Failed. Got Error Page: Current URL: {driver.current_url}"
                    )
                print("Waiting for portfolio page to load...")
                WebDriverWait(driver, 30).until(
                    expected_conditions.url_contains("summary")
                )
            # Make sure fidelity site is not in old view
            try:
                if "digital" not in driver.current_url:
                    print(f"Old view detected: {driver.current_url}")
                    driver.find_element(by=By.CSS_SELECTOR, value="#optout-btn").click()
                    WebDriverWait(driver, 10).until(check_if_page_loaded)
                    # Wait for page to be in new view
                    if "digital" not in driver.current_url:
                        WebDriverWait(driver, 60).until(
                            expected_conditions.url_contains("digital")
                        )
                    WebDriverWait(driver, 10).until(check_if_page_loaded)
                    print("Disabled old view!")
            except (TimeoutException, NoSuchElementException):
                print(
                    "Failed to disable old view! This might cause issues but maybe not..."
                )
            sleep(3)
            fidelity_obj.set_logged_in_object(name, driver)
            # Get account numbers, types, and balances
            account_dict = fidelity_account_info(driver, name=name)
            if account_dict is None:
                raise Exception(f"{name}: Error getting account info")
            for acct in account_dict:
                fidelity_obj.set_account_number(name, acct)
                fidelity_obj.set_account_type(name, acct, account_dict[acct]["type"])
                fidelity_obj.set_account_totals(
                    name, acct, account_dict[acct]["balance"]
                )
            print(f"Logged in to {name}!")
        except Exception as e:
            fidelity_error(driver, e)
            driver.close()
            driver.quit()
            return None
    return fidelity_obj


def fidelity_account_info(driver: webdriver, name="Fidelity") -> dict or None:
    try:
        # Get account holdings
        driver.get("https://digital.fidelity.com/ftgw/digital/portfolio/positions")
        # Wait for page load
        WebDriverWait(driver, 10).until(check_if_page_loaded)
        # Get account numbers via javascript
        WebDriverWait(driver, 10).until(
            expected_conditions.presence_of_element_located(
                (By.CLASS_NAME, "acct-selector__acct-num")
            )
        )
        account_numbers = javascript_get_classname(driver, "acct-selector__acct-num")
        print(f"Accounts: {account_numbers}")
        # Get account balances via javascript
        account_values = javascript_get_classname(driver, "acct-selector__acct-balance")
        print(f"Values: {account_values}")
        # Get account names via javascript
        account_types = javascript_get_classname(driver, "acct-selector__acct-name")
        print(f"Account Names: {account_types}")
        # Make sure all lists are the same length
        if not (
            len(account_numbers) == len(account_values)
            and len(account_numbers) == len(account_types)
        ):
            raise Exception(
                f"{name}: Error getting account info: Lists are not the same length"
            )
        # Construct dictionary of account numbers and balances
        account_dict = {}
        for i in range(len(account_numbers)):
            av = (
                account_values[i]
                .replace(" ", "")
                .replace("$", "")
                .replace(",", "")
                .replace("balance:", "")
            )
            account_dict[account_numbers[i]] = {
                "balance": float(av),
                "type": account_types[i],
            }
        return account_dict
    except Exception as e:
        fidelity_error(driver, e)
        return None


def fidelity_holdings(fidelity_o: Brokerage, loop=None):
    print()
    print("==============================")
    print("Fidelity Holdings")
    print("==============================")
    print()
    for key in fidelity_o.get_account_numbers():
        for account in fidelity_o.get_account_numbers(key):
            driver: webdriver = fidelity_o.get_logged_in_objects(key)
            try:
                driver.get(
                    f"https://digital.fidelity.com/ftgw/digital/portfolio/positions#{account}"
                )
                # Wait for page load
                WebDriverWait(driver, 10).until(check_if_page_loaded)
                # Get holdings via javascript
                WebDriverWait(driver, 10).until(
                    expected_conditions.presence_of_element_located(
                        (By.CLASS_NAME, "ag-pinned-left-cols-container")
                    )
                )
                stocks_list = javascript_get_classname(
                    driver, "ag-pinned-left-cols-container"
                )
                # Find 3 or 4 letter words surrounded by 2 spaces on each side
                for i in range(len(stocks_list)):
                    stocks_list[i].replace(" \n ", "")
                    stocks_list[i] = re.findall(
                        r"(?<=\s{2})[a-zA-Z]{3,4}(?=\s{2})", stocks_list[i]
                    )
                print(f"Stocks: {stocks_list}")
                holdings_info = javascript_get_classname(
                    driver, "ag-center-cols-container"
                )
                print(f"Holdings Info: {holdings_info}")
            except Exception as e:
                fidelity_error(driver, e)
                return None


def fidelity_transaction(fidelity_o: Brokerage, orderObj: stockOrder, loop=None):
    print()
    print("==============================")
    print("Fidelity")
    print("==============================")
    print()
    for s in orderObj.get_stocks():
        for key in fidelity_o.get_account_numbers():
            printAndDiscord(
                f"{key}: {orderObj.get_action()}ing {orderObj.get_amount()} of {s}",
                loop,
            )
            driver = fidelity_o.get_logged_in_objects(key)
            # Go to trade page
            driver.get(
                "https://digital.fidelity.com/ftgw/digital/trade-equity/index/orderEntry"
            )
            # Wait for page to load
            WebDriverWait(driver, 20).until(check_if_page_loaded)
            sleep(3)
            # Get number of accounts
            try:
                accounts_dropdown = driver.find_element(
                    by=By.CSS_SELECTOR, value="#dest-acct-dropdown"
                )
                driver.execute_script("arguments[0].click();", accounts_dropdown)
                WebDriverWait(driver, 10).until(
                    expected_conditions.presence_of_element_located(
                        (By.CSS_SELECTOR, "#ett-acct-sel-list")
                    )
                )
                test = driver.find_element(
                    by=By.CSS_SELECTOR, value="#ett-acct-sel-list"
                )
                accounts_list = test.find_elements(by=By.CSS_SELECTOR, value="li")
                print(f"Number of accounts: {len(accounts_list)}")
                number_of_accounts = len(accounts_list)
                # Click a second time to clear the account list
                driver.execute_script("arguments[0].click();", accounts_dropdown)
            except Exception as e:
                print(f"Error: No accounts foundin dropdown: {e}")
                traceback.print_exc()
                return
            # Complete on each account
            # Because of stale elements, we need to re-find the elements each time
            for x in range(number_of_accounts):
                try:
                    # Select account
                    accounts_dropdown_in = driver.find_element(
                        by=By.CSS_SELECTOR, value="#eq-ticket-account-label"
                    )
                    driver.execute_script("arguments[0].click();", accounts_dropdown_in)
                    WebDriverWait(driver, 10).until(
                        expected_conditions.presence_of_element_located(
                            (By.ID, "ett-acct-sel-list")
                        )
                    )
                    test = driver.find_element(by=By.ID, value="ett-acct-sel-list")
                    accounts_dropdown_in = test.find_elements(
                        by=By.CSS_SELECTOR, value="li"
                    )
                    account_label = accounts_dropdown_in[x].text
                    accounts_dropdown_in[x].click()
                    sleep(1)
                    # Type in ticker
                    ticker_box = driver.find_element(
                        by=By.CSS_SELECTOR, value="#eq-ticket-dest-symbol"
                    )
                    WebDriverWait(driver, 10).until(
                        expected_conditions.element_to_be_clickable(ticker_box)
                    )
                    ticker_box.send_keys(s)
                    ticker_box.send_keys(Keys.RETURN)
                    sleep(1)
                    # Check if symbol not found is displayed
                    try:
                        driver.find_element(
                            by=By.CSS_SELECTOR,
                            value="body > div.app-body > ap122489-ett-component > div > order-entry > div.eq-ticket.order-entry__container-height > div > div > form > div.order-entry__container-content.scroll > div:nth-child(2) > symbol-search > div > div.eq-ticket--border-top > div > div:nth-child(2) > div > div > div > pvd3-inline-alert > s-root > div > div.pvd-inline-alert__content > s-slot > s-assigned-wrapper",
                        )
                        print(f"Error: Symbol {s} not found")
                        return
                    except Exception:
                        pass
                    # Get ask/bid price
                    ask_price = (
                        driver.find_element(
                            by=By.CSS_SELECTOR,
                            value="#quote-panel > div > div.eq-ticket__quote--blocks-container > div:nth-child(2) > div > span > span",
                        )
                    ).text
                    bid_price = (
                        driver.find_element(
                            by=By.CSS_SELECTOR,
                            value="#quote-panel > div > div.eq-ticket__quote--blocks-container > div:nth-child(1) > div > span > span",
                        )
                    ).text
                    # If price is under $1, then we have to use a limit order
                    LIMIT = bool(float(ask_price) < 1 or float(bid_price) < 1)
                    # Set buy/sell
                    if orderObj.get_action() == "buy":
                        buy_button = driver.find_element(
                            by=By.CSS_SELECTOR,
                            value="#action-buy > s-root > div > label > s-slot > s-assigned-wrapper",
                        )
                        buy_button.click()
                    else:
                        sell_button = driver.find_element(
                            by=By.CSS_SELECTOR,
                            value="#action-sell > s-root > div > label > s-slot > s-assigned-wrapper",
                        )
                        sell_button.click()
                    # Set amount (and clear previous amount)
                    amount_box = driver.find_element(
                        by=By.CSS_SELECTOR, value="#eqt-shared-quantity"
                    )
                    amount_box.clear()
                    amount_box.send_keys(str(orderObj.get_amount()))
                    # Set market/limit
                    if not LIMIT:
                        market_button = driver.find_element(
                            by=By.CSS_SELECTOR,
                            value="#market-yes > s-root > div > label > s-slot > s-assigned-wrapper",
                        )
                        market_button.click()
                    else:
                        limit_button = driver.find_element(
                            by=By.CSS_SELECTOR,
                            value="#market-no > s-root > div > label > s-slot > s-assigned-wrapper",
                        )
                        limit_button.click()
                        # Set price
                        if orderObj.get_action() == "buy":
                            wanted_price = round(float(ask_price) + 0.01, 3)
                        else:
                            wanted_price = round(float(bid_price) - 0.01, 3)
                        price_box = driver.find_element(
                            by=By.CSS_SELECTOR, value="#eqt-ordsel-limit-price-field"
                        )
                        price_box.clear()
                        price_box.send_keys(wanted_price)
                    # Preview order
                    WebDriverWait(driver, 10).until(check_if_page_loaded)
                    sleep(1)
                    preview_button = driver.find_element(
                        by=By.CSS_SELECTOR, value="#previewOrderBtn"
                    )
                    preview_button.click()
                    # Wait for page to load
                    WebDriverWait(driver, 10).until(check_if_page_loaded)
                    sleep(3)
                    # Check for error popup and clear
                    try:
                        error_dismiss = driver.find_element(
                            by=By.XPATH,
                            value="(//button[@class='pvd-modal__close-button'])[3]",
                        )
                        driver.execute_script("arguments[0].click();", error_dismiss)
                    except NoSuchElementException:
                        pass
                    # Place order
                    if not orderObj.get_dry():
                        # Check for error popup and clear it if the
                        # account cannot sell the stock for some reason
                        try:
                            place_button = driver.find_element(
                                by=By.CSS_SELECTOR, value="#placeOrderBtn"
                            )
                            place_button.click()

                            # Wait for page to load
                            WebDriverWait(driver, 10).until(check_if_page_loaded)
                            sleep(1)
                            # Send confirmation
                            printAndDiscord(
                                f"{key} {account_label}: {orderObj.get_action()} {orderObj.get_amount()} shares of {s}",
                                loop,
                            )
                        except NoSuchElementException:
                            # Check for error
                            WebDriverWait(driver, 10).until(
                                expected_conditions.presence_of_element_located(
                                    (
                                        By.XPATH,
                                        "(//button[@class='pvd-modal__close-button'])[3]",
                                    )
                                )
                            )
                            error_dismiss = driver.find_element(
                                by=By.XPATH,
                                value="(//button[@class='pvd-modal__close-button'])[3]",
                            )
                            driver.execute_script(
                                "arguments[0].click();", error_dismiss
                            )
                            printAndDiscord(
                                f"{key} {account_label}: {orderObj.get_action()} {orderObj.get_amount()} shares of {s}. DID NOT COMPLETE! \nEither this account does not have enough shares, or an order is already pending.",
                                loop,
                            )
                        # Send confirmation
                    else:
                        printAndDiscord(
                            f"DRY: {key} {account_label}: {orderObj.get_action()} {orderObj.get_amount()} shares of {s}",
                            loop,
                        )
                    sleep(3)
                except Exception as err:
                    print(err)
                    traceback.print_exc()
                    driver.save_screenshot(
                        f"fidelity-login-error-{datetime.datetime.now()}.png"
                    )
                    continue
            print()
