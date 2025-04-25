import csv
import time
import os
import logging
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re

# Configure logging
logging.basicConfig(
    filename="scraper.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Set up Chrome with popup blocking disabled
options = uc.ChromeOptions()
options.add_argument("--disable-popup-blocking")

# Initialize WebDriver
driver = uc.Chrome(options=options)

# URL to scrape
url = "https://aca-prod.accela.com/HCFL/Cap/CapHome.aspx?module=Enforcement&TabName=Enforcement"
driver.get(url)

# Keywords to search for
keywords = [
    "overgrowth", "overgrown", "mold", "infested", "holes", "roof", "unstable",
    "broken", "boarded", "roof", "homeless", "squatter", "abandoned", "fire",
    "rats", "vacant", "vandalism"
]

time.sleep(40)  # 40-second delay for date setting

# Find and click the search button
search_button = driver.find_element(By.ID, "ctl00_PlaceHolderMain_btnNewSearch_container")
search_button.click()
time.sleep(10)  # Allow page to load

# CSV File Setup
main_csv = "HELP.csv"
failed_csv = "scraped12.csv"
csv_columns = ["Property Location", "Owner Name", "Project Description", "Phone Number"]
failed_columns = ["Project Description", "Reason"]

# Load existing records to prevent duplicates
processed_owners = set()  # Track owner names to avoid duplicates
failed_cases = set()

# Load main CSV by OWNER NAME (column index 1)
if os.path.exists(main_csv):
    try:
        with open(main_csv, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            for row in reader:
                if len(row) > 1:
                    processed_owners.add(row[1].strip().lower())  # Track owner names
    except Exception as e:
        print(f"Error reading {main_csv}: {e}")

# Load failed cases by description
if os.path.exists(failed_csv):
    try:
        with open(failed_csv, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            for row in reader:
                if len(row) > 0:
                    failed_cases.add(row[0].strip().lower())
    except Exception as e:
        print(f"Error reading {failed_csv}: {e}")

# Write headers if CSVs don't exist
for file, columns in [(main_csv, csv_columns), (failed_csv, failed_columns)]:
    if not os.path.exists(file):
        try:
            with open(file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(columns)
        except Exception as e:
            print(f"Error writing headers to {file}: {e}")

# Store original tab handle
original_tab = driver.current_window_handle

# Pagination counter
current_page = 1

# Set to store processed entries
processed_entries = []

try:
    while True:
        try:
            print(f"Processing page {current_page}...")
            # Get fresh list of rows each page
            rows = driver.find_elements(
                By.XPATH, "//tr[contains(@class, 'ACA_TabRow') or contains(@class, 'ACA_TabRow_Alternate')]"
            )

            for row_index in range(len(rows)):
                try:
                    row_number = row_index + 2
                    description_id = f"ctl00_PlaceHolderMain_dgvPermitList_gdvPermitList_ctl{row_number:02}_lblDescription"
                    description_element = driver.find_element(By.ID, description_id)
                    description = description_element.text.strip().lower()


                    # Check for keywords
                    if not any(kw in description for kw in keywords):
                        continue

                    print(f"Match found! Processing case: {description}")

                    # Store the current page number
                    match_page = current_page

                    # Duplicate the tab
                    current_url = driver.current_url
                    driver.execute_script(f"window.open('{current_url}')")
                    time.sleep(2)
                    driver.switch_to.window(driver.window_handles[-1])

                    # Navigate to the same page in the duplicated tab
                    for _ in range(match_page - 1):
                        next_button = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located(
                                (By.XPATH, "//a[contains(@class, 'aca_simple_text') and contains(text(), 'Next')]")
                            )
                        )
                        driver.execute_script("arguments[0].click();", next_button)
                        time.sleep(2)  # Wait for the page to load

                    # Re-find the same element in the duplicated tab
                    duplicate_row = driver.find_elements(
                        By.XPATH, "//tr[contains(@class, 'ACA_TabRow') or contains(@class, 'ACA_TabRow_Alternate')]"
                    )[row_index]

                    # Click the record in the duplicated tab
                    record_id = f"ctl00_PlaceHolderMain_dgvPermitList_gdvPermitList_ctl{row_number:02}_lblPermitNumber1"
                    record_element = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.ID, record_id))
                    )
                    record_element.click()
                    time.sleep(5)

                    # Extract information
                    property_address = "UNKNOWN"
                    try:
                        property_element = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CLASS_NAME, "NotBreakWord"))
                        )
                        property_address = property_element.text.strip()
                    except Exception as e:
                        print(f"Failed to extract property location: {e}")

                                    
                    owner_name = "UNKNOWN"
                    try:
                                            
                        owner_td = WebDriverWait(driver, 15).until(
                            EC.presence_of_element_located((By.XPATH, "//td[@style='vertical-align:top'][1]"))
                        )
                        raw_text = owner_td.get_attribute("innerText").strip()

                        # **Step 1: If there's a "*", take everything before it**
                        if "*" in raw_text:
                            owner_name = raw_text.split("*")[0].strip()
                        elif ";" in raw_text:
                            # **Step 2: If there's a ";", take everything before it**
                            owner_name = raw_text.split(";")[0].strip()
                        else:
                            # **Step 3: Otherwise, take the first non-empty line**
                            lines = raw_text.split("\n")
                            for line in lines:
                                line = line.strip()
                                # Skip empty lines and pure numbers
                                if not line or re.match(r"^\d{2,5}\s", line):
                                    continue  
                                owner_name = line
                                break  # Stop at first valid name

                        # **Step 4: Final Cleanup**
                        owner_name = owner_name.replace("*", "").strip()

                        # If we still got an empty name, set as UNKNOWN
                        if not owner_name:
                            owner_name = "UNKNOWN"
                    except Exception as e:
                             print(f"Failed to extract owner name: {e}")

                    # Check for duplicates or unknown owners
                    if owner_name.lower() in processed_owners:
                        print(f"Skipping duplicate owner: {owner_name}")
                        driver.close()
                        driver.switch_to.window(original_tab)
                        continue

                    if owner_name == "UNKNOWN":
                        print(f"Skipping unknown owner case: {description}")
                        with open(failed_csv, 'a', newline='', encoding='utf-8') as f:
                            csv.writer(f).writerow([description, "Unknown owner"])
                        failed_cases.add(description)
                        driver.close()
                        driver.switch_to.window(original_tab)
                        continue

                    # Add the entry to the processed_entries list
                    entry = [property_address, owner_name, description, ""]
                    processed_entries.append(entry)

                    # Add the owner name to the processed_owners set to avoid duplicates
                    processed_owners.add(owner_name.lower())
                    print(f"✅ Processed: {owner_name} - {description}")

                    # Close detail tab and return
                    driver.close()
                    driver.switch_to.window(original_tab)

                except Exception as e:
                    logging.error(f"Error processing row: {e}")
                    # Ensure we return to main tab on any error
                    if len(driver.window_handles) > 1:
                        driver.close()
                    driver.switch_to.window(original_tab)
                    continue

            # Pagination handling
            try:
                next_button = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//a[contains(@class, 'aca_simple_text') and contains(text(), 'Next')]")
                    )
                )
                driver.execute_script("arguments[0].click();", next_button)
                current_page += 1
                time.sleep(10)  # Increased wait for page reload
            except Exception as e:
                print("No more pages or pagination error")
                break

        except Exception as e:
            print(f"Critical error: {e}")
            break

except Exception as e:
    print(f"Script crashed: {e}")

finally:
    # Write all processed entries to the CSV file
    if processed_entries:
        try:
            with open(main_csv, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(processed_entries)
            print(f"✅ Saved {len(processed_entries)} entries to {main_csv}")
        except Exception as e:
            print(f"Error writing to {main_csv}: {e}")

    # Close browser
    driver.quit()