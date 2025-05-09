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

# Set up lambda invocation
lambda_client = boto3.client('lambda')

# Old Regex for Bates stamp
BATES_STAMP_REGEX: str = "(^[0][\\d]{5}\\^?$)"

# New Regex for Bates stamp
# Update regex to better match the format seen in the sample document
# BATES_STAMP_REGEX = r"(\d{2}CR\d{5}) // (\d{5})"

def lambda_handler(event, context):
    try:
        # Extract payload details
        access_token = event['access_token']
        file_id = event['file_id']
        original_file_name = event['original_file_name']
        folder_name = event['folder_name']  # Get folder name from payload
        user_id = event['user_id']  # Get user_id from the event

        if not access_token or not file_id or not original_file_name or not folder_name or not user_id:
            raise ValueError("Missing required payload information.")
        
        # Disk and case information        
        # Extract pdCaseNumber and disc from folder name
        pdCaseNumber, disc = extract_case_and_disc(folder_name)

        # Download file from Box
        file_content = download_file_from_box(file_id, access_token)

        # Extract Bates stamps
        bates_stamps = extract_bates_stamps(file_content)
            
        # Format the new file name
        new_file_name = format_file_name(bates_stamps, original_file_name, disc)
        
        # Update PdCasenumber
        event["pdCaseNumber"] = pdCaseNumber
        # Update event with new file name
        event["new_file_name"] = new_file_name

        logger.info(f"Updated event: {event}")

        target_lambda_function_name = os.environ.get('NEXT_LAMBDA')

        try:
            # Invoke the other Lambda function with the payload
            response = lambda_client.invoke(
                FunctionName=target_lambda_function_name,
                InvocationType='Event',  # 'Event' means asynchronous invocation
                Payload=json.dumps(event)
            )
            
            # Log the response from the Lambda invocation
            logger.info(f"Lambda invocation response: {response}")
            
            return {
                'statusCode': 200,
                'body': json.dumps('Successfully forwarded the information to the next Lambda function.')
            }
        
        # Check for error invoking lambda function
        except Exception as e:
            logger.error(f"Error invoking target Lambda function: {e}")
            # Invoke errorNotificationFunction
            error_payload = {
                'file_name': original_file_name,
                'error_reason': str(e),
                'user_id': user_id,  # Include user_id in the payload
                'file_link': f"https://app.box.com/file/{file_id}"  # Include file link
            }
            lambda_client.invoke(
                FunctionName='errorNotificationFunction',
                InvocationType='Event',
                Payload=json.dumps(error_payload))
            return {
                'statusCode': 200,
                'body': json.dumps(f'Error invoking target Lambda function: {str(e)}')
            }

    # Check for error in file processing
    except Exception as e:
        logger.error(f"Error in Lambda function: {e}")
        # Invoke errorNotificationFunction
        error_payload = {
            'file_name': original_file_name,
            'error_reason': str(e),
            'user_id': user_id,  # Include user_id in the payload
            'file_link': f"https://app.box.com/file/{file_id}"  # Include file link
        }
        lambda_client.invoke(
            FunctionName='errorNotificationFunction',
            InvocationType='Event',
            Payload=json.dumps(error_payload))
        return {
            'statusCode': 200,
            'body': json.dumps(f"Error: {str(e)}")
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
    page_count = 0
    pdf_document = fitz.open(stream=BytesIO(file_content), filetype="pdf")
    possible_stamps = []

    for page in pdf_document:
        page_count += 1

        # Get rectangle of bottom portion of page
        y0 = page.rect.height - (page.rect.height / 15)
        bottom_rect = fitz.Rect(page.rect.x0, y0, page.rect.x1, page.rect.y1) * page.derotation_matrix

        # Extract text from bottom rectangle
        extracted_text = page.get_text(clip=bottom_rect)
        extracted_words = str(extracted_text).split()

        # Log the extracted text for debugging
        logger.info(f"Page {page_count} extracted text: {extracted_text}")

        # Match Bates stamps using regex
        for word in extracted_words:
            if re.match(BATES_STAMP_REGEX, word):
                possible_stamps.append(word)

    return refine_bates_stamps(possible_stamps, page_count)

def refine_bates_stamps(possible_stamps: list[str], page_count: int) -> list[str]:
    refined_stamps: list[str] = []
    for stamp in possible_stamps:
        if stamp[-1] == "^":
            stamp = stamp[0:-1]
        refined_stamps.append(stamp)

    if refined_stamps:
        if len(refined_stamps) != page_count:
            raise ValueError(f"Inconsistent Bates stamps: Found {len(refined_stamps)} stamps for {page_count} pages.")
        if not is_consecutive(refined_stamps):
            raise ValueError("Inconsistent Bates stamps: Stamps are not consecutive.")
        if page_count == 1:
            refined_stamps = [refined_stamps[-1]]
    else:
        raise ValueError("No Bates stamps found in the document.")
    return refined_stamps

def is_consecutive(stamps: list[str]) -> bool:
    if len(stamps) == 1:
        return True

    prev_stamp = int(stamps[0])
    for stamp in stamps[1:]:
        if prev_stamp + 1 != int(stamp):
            return False
        prev_stamp = int(stamp)
    return True

def format_file_name(stamps: list[str], filename: str, disc: str) -> str:
    if len(stamps) > 1:
        name = f"{stamps[0]}-{stamps[-1]}_Disc {disc}_{filename}"
    elif len(stamps) == 1:
        name = f"{stamps[0]}_Disc {disc}_{filename}"
    else:
        raise ValueError("No Bates stamps found in the document.")
    return name

def extract_case_and_disc(folder_name):
    match = re.match(r"^(PD\d+)_(\d{2})$", folder_name)
    if not match:
        raise ValueError(f"Invalid folder name format: {folder_name}. Expected format: 'PDXXXXX_XX'.")
    
    pdCaseNumber, disc = match.groups()
    return pdCaseNumber, disc
