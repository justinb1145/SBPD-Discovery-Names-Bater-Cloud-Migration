import json
import re
import fitz  # PyMuPDF
import boto3
import logging
import requests
import os
from io import BytesIO

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Output bucket name
lambda_client = boto3.client('lambda')

# New Regex for Bates stamp
BATES_STAMP_REGEX = r"(?<=// )\d{5}"

# Get Next Lambda Function Name
target_lambda_function_name = os.environ.get('NEXT_LAMBDA')

# Get Error Lambda Function Name
error_lambda_function_name = os.environ.get('ERROR_LAMBDA')

def lambda_handler(event, context):
    try:
        # Initialize error field if it doesn't exist
        if "error" not in event:
            event["error"] = ""

        # Extract payload details
        access_token = event['access_token']
        file_id = event['file_id']
        original_file_name = event['original_file_name']
        folder_name = event['folder_name']
        user_id = event['user_id']

        if not access_token or not file_id or not original_file_name or not folder_name or not user_id:
            event["error"] += "\nMissing required payload information."
            raise ValueError("Missing required payload information.")

        # Disk and case information        
        try:
            pdCaseNumber, disc = extract_case_and_disc(folder_name, event)
        except ValueError as e:
            # Critical error: Invalid folder name format
            event["error"] += f"\n{e}"
            raise

        # Download file from Box
        file_content = download_file_from_box(file_id, access_token)

        # Extract Bates stamps
        bates_stamps = []
        try:
            bates_stamps = extract_bates_stamps(file_content)
        except ValueError as e:
            # Log the error and continue processing
            event["error"] += f"\n{e}"
            logger.error(f"Error extracting Bates stamps: {e}")

        # Format the new file name
        new_file_name = original_file_name  # Default to original file name if Bates stamps are invalid
        try:
            new_file_name = format_file_name(bates_stamps, original_file_name, disc)
        except ValueError as e:
            # Log the error and continue processing
            event["error"] += f"\n{e}"
            logger.error(f"Error formatting file name: {e}")

        # Update PdCasenumber and new file name in the event
        event["pdCaseNumber"] = pdCaseNumber
        event["new_file_name"] = new_file_name

        logger.info(f"Updated event: {event}")

        # Proceed to the next Lambda function
        try:
            response = lambda_client.invoke(
                FunctionName=target_lambda_function_name,
                InvocationType='Event',
                Payload=json.dumps(event)
            )
            logger.info(f"Lambda invocation response: {response}")
            return {
                'statusCode': 200,
                'body': json.dumps('Successfully forwarded the information to the next Lambda function.')
            }

        # Invoke error if lambda function is not triggered
        except Exception as e:
            event["error"] += f"\nError invoking target Lambda function: {e}"
            raise

    except Exception as e:
        logger.error(f"Error in Lambda function: {e}")
        # Notify user of critical error using error payload
        error_payload = {
            'file_name': original_file_name,
            'error_reason': event["error"].strip(),  # Include the specific error reason
            'user_id': user_id,
            'file_link': f"https://app.box.com/file/{file_id}"
        }
        lambda_client.invoke(
            FunctionName=error_lambda_function_name,
            InvocationType='Event',
            Payload=json.dumps(error_payload)
        )
        return {
            'statusCode': 200,
            'body': json.dumps(f"Error: {event['error'].strip()}")
        }

def download_file_from_box(file_id, access_token):
    # Box API endpoint to download the file
    file_url = f'https://api.box.com/2.0/files/{file_id}/content'
    headers = {
        'Authorization': f'Bearer {access_token}'
    }

    # Download the file
    logger.info(f"Fetching file from Box with URL: {file_url}")
    response = requests.get(file_url, headers=headers, stream=True)

    if response.status_code != 200:
        logger.error(f"Failed to fetch file from Box. Status Code: {response.status_code}")
        raise Exception(f"Failed to fetch file from Box. Status Code: {response.status_code}")

    logger.info("File downloaded successfully from Box.")
    return response.content  # Binary file data

def extract_bates_stamps(file_content: bytes) -> list[str]:
    # Initialize counter for PDF pages
    page_count = 0
    # Open PDF from memory stream using PyMuPDF
    pdf_document = fitz.open(stream=BytesIO(file_content), filetype="pdf")
    possible_stamps = []

    # Iterate through each page in the PDF
    for page in pdf_document:
        page_count += 1
        # Define rectangle for bottom portion of page (where Bates stamps typically appear)
        y0 = page.rect.height - (page.rect.height / 15)
        bottom_rect = fitz.Rect(page.rect.x0, y0, page.rect.x1, page.rect.y1) * page.derotation_matrix

        # Extract text from bottom rectangle
        extracted_text = page.get_text(clip=bottom_rect)
        extracted_words = str(extracted_text).split()

        # Log the extracted text for debugging
        logger.info(f"Page {page_count} extracted text: {extracted_text}")

        # Match Bates stamps using regex
        for match in re.findall(BATES_STAMP_REGEX, " ".join(extracted_words)):
            possible_stamps.append(match)

    return refine_bates_stamps(possible_stamps, page_count)

def refine_bates_stamps(possible_stamps: list[str], page_count: int) -> list[str]:
    refined_stamps: list[str] = []

    # Clean up any stamps that end with "^" character
    for stamp in possible_stamps:
        if stamp[-1] == "^":
            stamp = stamp[0:-1]
        refined_stamps.append(stamp)

    # Validate the collection of stamps
    if refined_stamps:
        # CHeck if we have the right number of stamps (one per page)
        if len(refined_stamps) != page_count:
            raise ValueError(f"Inconsistent Bates stamps: Found {len(refined_stamps)} stamps for {page_count} pages.")

        # CHeck if stamps are in sequential order
        if not is_consecutive(refined_stamps):
            raise ValueError("Inconsistent Bates stamps: Stamps are not consecutive.")

        # For single-page documents, use only the last stamp found
        if page_count == 1:
            refined_stamps = [refined_stamps[-1]]
    else:
        # No stamp found - raise error
        raise ValueError("No Bates stamps found in the document.")
    return refined_stamps

def is_consecutive(stamps: list[str]) -> bool:
    # Single stamp is considered valid
    if len(stamps) == 1:
        return True

    # Check if each stamp is exactly one more than the previous
    prev_stamp = int(stamps[0])
    for stamp in stamps[1:]:
        if prev_stamp + 1 != int(stamp):
            return False
        prev_stamp = int(stamp)
    return True

def format_file_name(stamps: list[str], filename: str, disc: str) -> str:
    # Check if Bates stamps exist, if not, return default name
    name = filename
    if not stamps:
        name = f"00000_Disc {disc}_{filename}"
    elif len(stamps) > 1:
        name = f"{stamps[0]}-{stamps[-1]}_Disc {disc}_{filename}"
    elif len(stamps) == 1:
        # Single-page documednt: use single stamp format
        name = f"{stamps[0]}_Disc {disc}_{filename}"
    return name

def extract_case_and_disc(folder_name, event):
    # Check if the folder name starts with "PD" followed by digits
    if not re.match(r"^PD\d+", folder_name):
        raise ValueError(f"Invalid folder name format: {folder_name}. Folder name must start with 'PD' followed by digits.")

    # Check if the folder name has the correct format with "_XX" suffix
    match = re.match(r"^(PD\d+)_(\d{2})$", folder_name)
    if not match:
        # Non-critical error: Missing or invalid "_XX" suffix
        # Assign default disc value and continue
        event["error"] += f"\nInvalid folder name format: {folder_name}. Expected format: 'PDXXXXX_XX'. Assigning default disc value '00'."
        pdCaseNumber = re.match(r"^(PD\d+)", folder_name).group(1)
        disc = "00"
        return pdCaseNumber, disc
    
    pdCaseNumber, disc = match.groups()
    return pdCaseNumber, disc
