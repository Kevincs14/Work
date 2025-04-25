from seleniumbase import Driver
import time
import csv
import os
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
import re
from fuzzywuzzy import fuzz
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

# Define Hillsborough County cities
cities = ["Tampa", "St. Petersburg", "Clearwater", "Brandon", "Plant City", 
          "Riverview", "Carrollwood", "Lutz", "Apollo Beach", "Gibsonton", 
          "Thonotosassa", "Mango", "East Lake-Orient Park", "Seffner", "Valrico"]

def clean_address_string(address):
    return " ".join(address.replace('*', '').split()).strip().lower()

import re

def split_address_and_city(address):
    # Clean out unwanted hexadecimal strings (e.g., '0x444') and carriage return artifacts (e.g., '_x000D_')
    cleaned_address = re.sub(r'\b0x[0-9a-fA-F]+\b', '', address)
    cleaned_address = re.sub(r'_x[0-9a-fA-F]{4}_', '', cleaned_address)

    for city in cities:
        # Also clean out any _x000D_ in city names
        city_cleaned = re.sub(r'\b0x[0-9a-fA-F]+\b', '', city)
        city_cleaned = re.sub(r'_x[0-9a-fA-F]{4}_', '', city_cleaned)

        if city_cleaned in cleaned_address:
            city_index = cleaned_address.index(city_cleaned)
            street_address = cleaned_address[:city_index].strip()
            city_zip = cleaned_address[city_index:].strip()

            # Remove any unwanted hexadecimal parts from city_zip
            city_zip = re.sub(r'\b0x[0-9a-fA-F]+\b', '', city_zip)
            city_zip = re.sub(r'_x[0-9a-fA-F]{4}_', '', city_zip)

            # Find the zip code in city_zip
            zip_code_match = re.search(r'\d{5}(?:-\d{4})?', city_zip)
            zip_code = zip_code_match.group(0) if zip_code_match else None

            # Remove the zip code part from city name if it exists
            city_name = city_zip.replace(zip_code, '').strip() if zip_code else city_zip.strip()
            return street_address, city_name, zip_code
    
    return None, None, None



def clean_name(name):
    """Remove middle names or initials from the name."""
    parts = name.split()
    if len(parts) > 2:
        return f"{parts[0]} {parts[-1]}"
    return name

def split_hyphenated_name(name):
    """Split hyphenated names into individual words."""
    return name.replace('-', ' ')

def name_matches(query, candidate):
    """
    Check if the query name matches the candidate name using:
    1. Exact match of the full name.
    2. Fuzzy matching with a similarity threshold.
    3. Combined condition: At least one exact word match AND at least three consecutive letters match.
    """
    # Clean and split names
    query_cleaned = split_hyphenated_name(clean_name(query.lower()))
    candidate_cleaned = split_hyphenated_name(clean_name(candidate.lower()))
    
    print(f"Query: {query_cleaned}")
    print(f"Candidate: {candidate_cleaned}")
    
    # Condition 1: Exact match of full name
    if query_cleaned == candidate_cleaned:
        print("✅ Exact match of full name.")
        return True
    
    # Condition 2: Fuzzy matching
    similarity_score = fuzz.token_sort_ratio(query_cleaned, candidate_cleaned)
    print(f"Fuzzy similarity score: {similarity_score}")
    if similarity_score >= 80:
        print("✅ Fuzzy match (score >= 80).")
        return True
    
    # Condition 3: Combined condition (exact word match AND three consecutive letters match)
    query_words = set(query_cleaned.split())
    candidate_words = set(candidate_cleaned.split())

    # Find exact word matches
    common_words = query_words & candidate_words  # Intersection of sets
    if not common_words:
        print(f"❌ No exact word match between {query_cleaned} and {candidate_cleaned}.")
        return False

    # Remove exact matches from consideration for three-letter matching
    query_words -= common_words
    candidate_words -= common_words

    # Check for at least three consecutive letters match (only among non-exact-match words)
    for q_word in query_words:
        for c_word in candidate_words:
            for i in range(len(q_word) - 2):
                substring = q_word[i:i+3]
                if substring in c_word:
                    print(f"✅ Combined match: exact word '{list(common_words)}' and three consecutive letters '{substring}'.")
                    return True

    # No match found
    print("❌ No combined match found.")
    return False


def handle_captcha(driver):
    """Handle CAPTCHA using uc_gui_click_captcha()."""
    try:
        print("⚠️ CAPTCHA detected. Attempting to bypass...")
        driver.uc_gui_click_captcha()
        print("✅ CAPTCHA bypassed.")
    except Exception as e:
        print(f"❌ Error handling CAPTCHA: {e}")

def search_truepeoplesearch(driver, owner_name, property_id):
    start_time = time.time()
    try:
        print(f"🔍 Searching for owner: {owner_name} at {property_id}...")
        driver.get("https://www.truepeoplesearch.com/")
        time.sleep(2)

        address_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".search-type-addr .search-type-link"))
        )
        address_tab.click()
        time.sleep(1)

        search_bar = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "id-d-addr"))
        )

       
        
        street_address, city_name, zip_code = split_address_and_city(property_id)
        if not street_address or not city_name:
            print(f"⚠️ Could not parse address: {property_id}")
            return None
        
        search_bar.clear()
        search_bar.send_keys(street_address)
        time.sleep(1)

        form_container = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.ID, "searchFormAddressDesktop"))
        )

        city_zip_input = form_container.find_element(By.XPATH, './/input[@aria-label="City, State or Zip"]')
        formatted_city_zip = f"{city_name} FL {zip_code}" if zip_code else f"{city_name} FL"
        driver.execute_script(
            "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));",
            city_zip_input, formatted_city_zip
        )
        time.sleep(1)
        
        submit_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "btnSubmit-d-addr"))
        )
        driver.execute_script("arguments[0].click();", submit_button)
        time.sleep(2)
    
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '#px-captcha'))
            )
            handle_captcha(driver)
        except TimeoutException:
            print("✅ No CAPTCHA detected after submission. Proceeding...")

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.card"))
            )
        except TimeoutException:
            print(f"⚠️ No search results found for {owner_name}.")
            return None

        result_containers = driver.find_elements(By.CSS_SELECTOR, "div.card")
        if not result_containers:
            print(f"⚠️ No search results found for {owner_name}.")
            return None

        for container in result_containers:
            try:
                name_element = container.find_element(By.CSS_SELECTOR, "div.h4")
                name_text = name_element.text.strip()
                if name_matches(owner_name, name_text):
                    print(f"✅ Found matching owner name: {name_text}")
                    view_details_button = container.find_element(By.CSS_SELECTOR, 'a[aria-label="View All Details"]')
                    driver.execute_script("arguments[0].click();", view_details_button)
                    print(f"➡️ Clicking 'View All Details' for {name_text}...")
                    time.sleep(2)

                    try:
                        # Grab all phone numbers on the page
                        phone_number_elements = WebDriverWait(driver, 15).until(
                            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "span[itemprop='telephone']"))
                        )
                        if not phone_number_elements:
                            print(f"⚠️ No phone numbers found for {name_text}.")
                            driver.back()
                            return None
                        
                        if os.path.exists("truepople6.csv"):
                            with open("truepople6.csv", mode="r", encoding="utf-8") as file:
                                if any(phone_number1 in row for row in csv.reader(file)):
                                    print(f"⚠️ Phone number {phone_number1} already exists. Skipping...")
                                    driver.back()
                                    return None

                        # Collect all phone numbers into a single string, separated by commas
                        phone_number1 = phone_number_elements[1].text.strip()
                        
                        print(f"📞 Found phone numbers: {phone_number1}")
                        return phone_number1

                    except TimeoutException:
                        print(f"⚠️ Phone numbers not found for {name_text}.")
                        driver.back()
                        return None

            except NoSuchElementException:
                continue

        print(f"❌ No matching owner found for {owner_name}.")
        driver.back()
        return None

    except TimeoutException:
        print("⏳ Timeout occurred during search.")
        driver.back()
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        driver.back()
        return None
    finally:
        total_time = time.time() - start_time
        if total_time > 48:
            print(f"⚠️ Process took too long ({total_time:.2f} seconds). Reshooting...")
            return None

def load_existing_entries(csv_file_path):
    """Load existing entries from the CSV file into memory."""
    existing_entries = set()
    if os.path.exists(csv_file_path):
        with open(csv_file_path, mode='r', encoding='utf-8') as file:
            reader = csv.reader(file)
            next(reader, None)
            for row in reader:
                if len(row) >= 4:
                    existing_entries.add((row[0].lower(), row[1].lower(), row[3]))
    return existing_entries

def entry_exists(owner_name, property_address, phone_number):
    csv_file_path = "works.csv"
    if not os.path.exists(csv_file_path):
        return False
    try:
        with open(csv_file_path, mode='r', encoding='utf-8') as file:
            reader = csv.reader(file)
            next(reader, None)
            for row in reader:
                if len(row) >= 4:
                    existing_owner, existing_address, _, existing_phone = row
                    if (existing_owner.lower() == owner_name.lower() and
                        existing_address.lower() == property_address.lower() and
                        existing_phone == phone_number):
                        return True
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
    return False

def save_to_new_csv(data_list):
    csv_file_path = "org2.csv"
    file_exists = os.path.exists(csv_file_path)
    try:
        with open(csv_file_path, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            
            # Define headers
            headers = ['owner_name', 'property_address', 'description', 'phone_number']
            
            # Write headers if the file doesn't exist
            if not file_exists:
                writer.writerow(headers)
            
            # Write data rows
            for data in data_list:
                # Ensure the data dictionary contains all expected keys
                if all(key in data for key in headers):
                    if not entry_exists(data['owner_name'], data['property_address'], data['phone_number']):
                        writer.writerow([data['owner_name'], data['property_address'], data['description'], data['phone_number']])
                        print(f"✅ Saved {data['owner_name']}'s data to 'truepeople.csv'.")
                    else:
                        print(f"⚠️ Entry already exists for {data['owner_name']} at {data['property_address']}.")
                else:
                    print(f"⚠️ Missing data for {data.get('owner_name', 'unknown')}. Skipping...")
    except Exception as e:
        print(f"❌ Failed to write to CSV: {e}")

def process_entries(entries):
    """Process multiple entries using one persistent browser session."""
    driver = Driver(uc=True, headless=False)
    # One-time wait for manual adblocker setup (25 seconds)
    print("Waiting 25 seconds for manual adblocker setup on this browser instance...")
    time.sleep(35)
    results = []
    try:
        for entry in entries:
            owner_name, property_id, description = entry
            time.sleep(random.uniform(1, 3))
            phone_number = search_truepeoplesearch(driver, owner_name, property_id)
            if phone_number:
                results.append({
                    "owner_name": owner_name,
                    "property_address": property_id,
                    "description": description,
                    "phone_number": phone_number
                })
    except Exception as e:
        print(f"❌ Error processing entries: {e}")
    finally:
        driver.quit()
    return results
    
def main():
    csv_file_path = "truebruh.xlsx"
    try:
        # Read the Excel file and explicitly set the header row
        df = pd.read_excel(csv_file_path, header=0)
        df.reset_index(drop=True, inplace=True)  # Reset the index to ensure sequential row numbers

        # Debugging: Print the first 5 rows, last 5 rows, and total rows
        print("First 5 rows of the DataFrame:")
        print(df.head())

        print("\nLast 5 rows of the DataFrame:")
        print(df.tail())

        print(f"\nTotal rows in the DataFrame: {len(df)}")

        # Extract entries as tuples: (owner_name, property_id, description)
        entries = []
        for index, row in df.iterrows():
            # Debugging: Print the current row number and row data
            print(f"🔄 Processing Row {index + 1}:")
            print(f"   Owner Name: {row.iloc[1] if len(row) > 1 else 'N/A'}")
            print(f"   Property ID: {row.iloc[0] if len(row) > 0 else 'N/A'}")
            print(f"   Description: {row.iloc[2] if len(row) > 2 else 'N/A'}")
            print("-" * 40)  # Separator for readability

            owner_name = str(row.iloc[1]) if len(row) > 1 else ""
            property_id = str(row.iloc[0]) if len(row) > 0 else ""
            description = str(row.iloc[2]) if len(row) > 2 else ""
            entries.append((owner_name, property_id, description))
        
        # Debugging: Confirm all entries are loaded
        print(f"Total entries to process: {len(entries)}")
        for i, entry in enumerate(entries):
            print(f"Entry {i + 1}: {entry}")

        # Load existing entries from CSV to avoid duplicates
        existing_entries = load_existing_entries("truepeople.csv")
        
        # Process entries using ThreadPoolExecutor
        results = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(process_entries, entries),
            ]
            for future in as_completed(futures):
                group_results = future.result()
                if group_results:
                    results.extend(group_results)
                    print("✅ Saving results to CSV...")
                    save_to_new_csv(results)
        
    except Exception as e:
        print(f"❌ Error reading Excel file: {e}")


if __name__ == "__main__":
    main()









    