import argparse
import csv
import logging
import re
import requests
import os
from retrying import retry
from tqdm import tqdm
from xml.etree import ElementTree as ET


# Define a vocabulary mapping for attribute names
ATTRIBUTE_VOCABULARY = {
    "codiceFiscale": ["codiceFiscale", "identificativoFiscaleEstero"],
    # Add more mappings as needed
}


def get_attribute_value(element, attribute_name):
    """Search for all known variations of an attribute in the dictionary.
    Return the content if found, otherwise None.
    """
    for variant in ATTRIBUTE_VOCABULARY.get(attribute_name, [attribute_name]):
        attribute_element = element.find(variant)
        if attribute_element is not None:
            return attribute_element.text
    return None


def parse_lotto_xml(xml_content):
    """Parse a standard XML file with lotto elements."""
    try:
        root = ET.fromstring(xml_content)
        results = []
        # Iterate over each "lotto" element
        for lotto in root.findall(".//lotto"):
            ente = lotto.find("./strutturaProponente/denominazione").text
            cf_ente = lotto.find("./strutturaProponente/codiceFiscaleProp").text
            cig = lotto.find("./cig").text
            partecipanti = [
                get_attribute_value(p, "codiceFiscale")
                for p in lotto.findall("./partecipanti/partecipante")
            ]
            aggiudicatari = [
                get_attribute_value(a, "codiceFiscale")
                for a in lotto.findall("./aggiudicatari/aggiudicatario")
            ]
            results.append((ente, cf_ente, cig, partecipanti, aggiudicatari))
        return results
    except ET.ParseError as e:
        logging.error(f"Error parsing lotto XML: {e}")
        return None


def process_dataset_xml(xml_content, csv_filename, parent_xml_link):
    """Parse a collection XML file that links to the standard lotto XMLs."""
    try:
        root = ET.fromstring(xml_content)
        links = [link.text for link in root.findall(".//linkDataset")]
        # Process each linked lotto XML file
        for link in links:
            # Avoid looping
            if link != parent_xml_link:
                process_xml_link(link, csv_filename)
    except ET.ParseError as e:
        logging.error(f"Error parsing collection XML: {e}")
        return None


@retry(stop_max_attempt_number=3, wait_fixed=1000, stop_max_delay=5000)
def make_request(xml_link):
    response = requests.get(xml_link, timeout=5)
    response.raise_for_status()  # Raise an error for bad responses (4xx and 5xx)
    # override encoding by real educated guess as provided by chardet
    response.encoding = response.apparent_encoding
    logging.info(f"Successfully fetched XML content from {xml_link}")
    return response


def process_xml_link(xml_link, csv_filename):
    """Try to access the contents of the XML link, identify the type,
    and update a CSV file with what is retrieved.
    """
    try:
        response = make_request(xml_link)
    except (requests.exceptions.RequestException, Exception) as e:
        logging.error(f"Error accessing {xml_link}: {e}")
        return 1
    try:
        xml_content = response.text
        # Detect XML structure type
        root = ET.fromstring(xml_content)
        if root.find(".//lotto") is not None:
            # Process as the first type of XML with lotto elements
            parsed_data = parse_lotto_xml(xml_content)
        elif root.find(".//dataset") is not None:
            # Process as the second type of XML with dataset elements containing links
            parsed_data = process_dataset_xml(xml_content, csv_filename, xml_link)
        else:
            logging.error(f"Unknown XML structure in {xml_link}")
            return
        if parsed_data:
            update_csv(csv_filename, parsed_data)
            logging.info(f"Processed: {xml_link}")
        return 0
    except Exception as e:
        logging.error(f"Error processing {xml_link}: {e}")
        return 2


def update_csv(csv_filename, data):
    """Append the processed data to a CSV file."""
    with open(csv_filename, "a", newline="") as csvfile:
        csvwriter = csv.writer(csvfile)
        for row in data:
            ente, cf_ente, cig, partecipanti, aggiudicatari = row
            # If there is a winner, but no participant, set the winner as the participant
            if len(aggiudicatari) > 0 and len(partecipanti) == 0:
                partecipanti = aggiudicatari.copy()
            for partecipante in partecipanti:
                winner = 1 if partecipante in aggiudicatari else 0
                csvwriter.writerow([ente, cf_ente, cig, partecipante, winner])


def update_status_csv(csv_filename, row):
    """Append the data access status to a CSV file."""
    with open(csv_filename, "a", newline="") as csvfile:
        csvwriter = csv.writer(csvfile)
        csvwriter.writerow(row)


def check_files_existence(args):
    """Make sure the user wants to delete already existing files before proceeding."""
    file_paths = [args.output_filename, args.status_filename, args.log_file_path]
    existing_files = [file for file in file_paths if os.path.exists(file)]
    if existing_files:
        print("The specified files already exists:")
        for file in existing_files:
            print(f"- {file}")
        user_input = input("Do you want to delete them? [y]/n): ").lower()
        if user_input == "" or user_input.lower() == "y":
            # Remove existing files
            for file in existing_files:
                os.remove(file)
            print("Existing files removed. Proceeding with the program.")
        else:
            print("Execution canceled.")
            return False
    return True


def parse_args():
    parser = argparse.ArgumentParser(description="Process XML data and save results to CSV.")
    parser.add_argument("input_filename", help="Path to the XML input file.")
    parser.add_argument("output_filename", help="Path to the CSV output file.")
    parser.add_argument("status_filename", help="Path to the CSV with link status.")
    parser.add_argument("log_file_path", help="Path to the log output file.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if check_files_existence(args):
        print("All specified files do not exist or have been removed, proceeding.")
    else:
        exit()
    # Configure logging
    logging.basicConfig(
        filename=args.log_file_path,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%d-%m-%Y %H:%M:%S",
        level=logging.INFO,
    )
    # Load the XML file
    input_tree = ET.parse(args.input_filename)
    input_root = input_tree.getroot()
    match = re.search(r"l190-(\d{4})\.xml", args.input_filename)
    if match:
        year = match.group(1)
    for i, comunicazione in enumerate(tqdm(input_root.findall("comunicazione"))):
        try:
            cf_ente = comunicazione.find("codiceFiscale").text.strip()
            name_ente = comunicazione.find("ragioneSociale").text
            name_ente = name_ente.strip() if name_ente is not None else ""
            url = comunicazione.find("url").text.strip()
        except Exception as e:
            logging.error(f"Error processing comunicazione {i}: {e}")
            continue
        # fix not valid urls
        if not url.startswith("http"):
            url = "http://" + url
        logging.info(f"Processing {url}")
        return_code = process_xml_link(url, args.output_filename)
        update_status_csv(args.status_filename, (year, cf_ente, name_ente, url, return_code))
