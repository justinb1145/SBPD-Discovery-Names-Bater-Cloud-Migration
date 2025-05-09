import json
import logging
import boto3
import os
import hmac
import hashlib
import base64
import datetime
import time
from typing import Dict
from typing import List
from typing import Optional

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Set up AWS Lambda client for invoking another Lambda function
lambda_client = boto3.client('lambda')

# Get Next Lambda Function Name
target_lambda_function_name = os.environ.get('NEXT_LAMBDA')

# Get Error Lambda Function Name
error_lambda_function_name = os.environ.get('ERROR_LAMBDA')

# Set up AWS Secrets Manager client
secrets_client = boto3.client('secretsmanager')

# Define the maximum allowed file size in bytes (64MB)
MAX_FILE_SIZE_BYTES = 64 * 1024 * 1024  # 64MB

Date = datetime.date
DateTime = datetime.datetime

def get_box_skill_keys():
    """Fetches Box Skill primary and secondary keys from AWS Secrets Manager."""
    secret_name = os.environ.get('BOX_SECRET_NAME')
    if not secret_name:
        raise ValueError("BOX_SECRET_NAME environment variable is not set.")
    
    try:
        # Get the secret value from AWS Secrets Manager
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret_string = response.get('SecretString')

        if not secret_string:
            raise ValueError("SecretString is empty.")

        # Parse the JSON secret
        secret_data = json.loads(secret_string)
        box_skill_settings = secret_data.get('boxSkillSettings', {})

        primary_key = box_skill_settings.get('primaryKey')
        secondary_key = box_skill_settings.get('secondaryKey')

        if not primary_key or not secondary_key:
            raise ValueError("Box Skill keys are missing in Secrets Manager.")

        return primary_key, secondary_key
    except Exception as e:
        logger.error(f"Failed to retrieve Box Skill keys: {e}")
        raise

def lambda_handler(event, context):
    try:
        logger.info(f"Received event: {json.dumps(event)}")

        # Extract headers and body
        headers = event.get('headers')
        body = event.get('body')
        
        # Check the types of headers and body
        if not isinstance(headers, dict):
            logger.error("Invalid type for headers. Expected Dict[str, str].")
            return {
                'statusCode': 400,
                'body': json.dumps('Invalid type for headers. Expected Dict[str, str].')
            }
        
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
            logger.error("Invalid content in headers. Expected all keys and values to be strings.")
            return {
                'statusCode': 400,
                'body': json.dumps('Invalid content in headers. Expected all keys and values to be strings.')
            }

        if not isinstance(body, str):
            logger.error("Invalid type for body. Expected str.")
            return {
                'statusCode': 400,
                'body': json.dumps('Invalid type for body. Expected str.')
            }

        # Retrieve Box Skill keys
        primary_key, secondary_key = get_box_skill_keys()
        
        logger.info(f"Primary: {primary_key}\n Secondary: {secondary_key}")

        logger.info(f"Headers: {headers}")

        logger.info(f"Body: {body}")
        
        # Extract the 'max-age' value from the cache-control header
        cache_control_header = headers.get('cache-control', '')

        max_age = 600  # Default value if 'max-age' is not present or parse fails

        # If the 'cache-control' header is in the format 'max-age=xxx', extract the value
        if 'max-age' in cache_control_header:
            max_age = int(cache_control_header.split('max-age=')[1].split()[0])

        logger.info(f"Max-Age: {max_age}")

        # Now pass max_age to the validate_message method
        valid = validate_message(
            body,
            headers,
            primary_key,
            secondary_key=secondary_key,
            max_age=max_age  # Pass the extracted max-age value here
        )

        # Log the validation result
        logger.info(f"Webhook signature validation result: {valid}")

        # Validate webhook signature
        if not valid:
            logger.error("Invalid webhook signature. Possible security risk.")
            return {
                'statusCode': 400,
                'body': json.dumps('Invalid webhook signature.')
            }

        logger.info("Webhook signature validated successfully.")

        # Parse the event body
        body = json.loads(event['body'])

        # Extract the necessary data
        access_token = body.get('token', {}).get('read', {}).get('access_token')
        file_id = body.get('source', {}).get('id')
        original_file_name = body.get('source', {}).get('name')
        parent_folder_id = body.get('source', {}).get('parent', {}).get('id')
        user_id = body.get('event', {}).get('created_by', {}).get('id')
        file_size = body.get('source', {}).get('size')  # Extract file size

        # Log the extracted information for verification
        # logger.info(f"Access Token: {access_token}")
        # logger.info(f"File ID: {file_id}")
        # logger.info(f"Original File Name: {original_file_name}")
        # logger.info(f"Parent Folder ID: {parent_folder_id}")
        # logger.info(f"User ID: {user_id}")
        # logger.info(f"File Size: {file_size} bytes")

        # Check if any of the required data is missing
        if not access_token or not file_id or not original_file_name or not parent_folder_id:
            logger.error("Missing required information (access token, file ID, file name, or parent folder ID).")
            return {
                'statusCode': 400,
                'body': json.dumps('Missing required information.')
            }

        # Check if the file size exceeds the maximum allowed size
        if file_size > MAX_FILE_SIZE_BYTES:
            logger.error(f"File size exceeds the maximum allowed size of {MAX_FILE_SIZE_BYTES} bytes.")
            # Invoke errorNotificationFunction
            error_payload = {
                'file_name': original_file_name,
                'error_reason': f"File size exceeds the maximum allowed size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.",  # Convert bytes to MB
                'user_id': user_id,  # Include user_id in the payload
                'file_link': f"https://app.box.com/file/{file_id}"  # Include file link
            }
            lambda_client.invoke(
                FunctionName=error_lambda_function_name,
                InvocationType='Event',
                Payload=json.dumps(error_payload))
            return {
                'statusCode': 200,
                'body': json.dumps(f'File size exceeds the maximum allowed size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.')
            }

        # Prepare the payload to pass on to the next Lambda function
        payload = {
            "access_token": access_token,
            "file_id": file_id,
            "original_file_name": original_file_name,
            "parent_folder_id": parent_folder_id,
            "user_id": user_id
        }

        try:
            # Invoke the other Lambda function with the payload
            response = lambda_client.invoke(
                FunctionName=target_lambda_function_name,
                InvocationType='Event',  # 'Event' means asynchronous invocation
                Payload=json.dumps(payload)
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
                FunctionName=error_lambda_function_name,
                InvocationType='Event',
                Payload=json.dumps(error_payload))
            return {
                'statusCode': 200,
                'body': json.dumps(f'Error invoking target Lambda function: {str(e)}')
            }
    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}")
        return {
            'statusCode': 200,
            'body': json.dumps(f"Internal server error: {str(e)}")
        }

def validate_message(
        body: str,
        headers: Dict[str, str],
        primary_key: str,
        *,
        secondary_key: Optional[str] = None,
        max_age: Optional[int] = 600
    ) -> bool:
        """
        Validate a webhook message by verifying the signature and the delivery timestamp
        :param body: The request body of the webhook message
        :param headers: The headers of the webhook message
        :param primary_key: The primary signature to verify the message with
        :param secondary_key: The secondary signature to verify the message with, defaults to None
        :param max_age: The maximum age of the message in seconds, defaults to 10 minutes, defaults to 600
        """
        # Get the delivery timestamp from headers
        delivery_timestamp: DateTime = date_time_from_string(headers.get('box-delivery-timestamp'))
        current_epoch: int = get_epoch_time_in_seconds()

        logger.info(f"Delivery timestamp: {delivery_timestamp}")
        logger.info(f"Current epoch time: {current_epoch}")

        # Check if the message is within the allowed age range
        if current_epoch - max_age > date_time_to_epoch_seconds(delivery_timestamp):
            logger.info("Message is too old: exceeds max_age")
            return False
        if date_time_to_epoch_seconds(delivery_timestamp) > current_epoch:
            logger.info("Message timestamp is in the future")
            return False

        # Check if the primary signature matches
        primary_signature = headers.get('box-signature-primary')
        if primary_signature:
            computed_signature = _compute_signature(bytes(body, "utf-8"), headers, primary_key)
            if computed_signature == primary_signature:
                logger.info("Primary signature valid.")
                return True
            else:
                logger.info(f"Primary signature mismatch: {computed_signature} != {primary_signature}")
        else:
            logger.info("Primary signature not found in headers.")

        # Check if the secondary signature matches
        if secondary_key:
            secondary_signature = headers.get('box-signature-secondary')
            if secondary_signature:
                computed_signature = _compute_signature(bytes(body, "utf-8"), headers, secondary_key)
                if computed_signature == secondary_signature:
                    logger.info("Secondary signature valid.")
                    return True
                else:
                    logger.info(f"Secondary signature mismatch: {computed_signature} != {secondary_signature}")
            else:
                logger.info("Secondary signature not found in headers.")

        logger.info("Message validation failed.")
        return False

def _compute_signature(body: bytes, headers: dict, signature_key: str) -> Optional[str]:
    """
    Computes the Hmac for the webhook notification given one signature key.

    :param body:
        The encoded webhook body.
    :param headers:
        The headers for the `Webhook` notification.
    :param signature_key:
        The `Webhook` signature key for this application.
    :return:
        An Hmac signature.
    """
    if signature_key is None:
        return None
    if headers.get('box-signature-version') != '1':
        return None
    if headers.get('box-signature-algorithm') != 'HmacSHA256':
        return None

    encoded_signature_key = signature_key.encode('utf-8')
    encoded_delivery_time_stamp = headers.get('box-delivery-timestamp').encode('utf-8')
    new_hmac = hmac.new(encoded_signature_key, digestmod=hashlib.sha256)
    new_hmac.update(body + encoded_delivery_time_stamp)
    signature = base64.b64encode(new_hmac.digest()).decode()
    return signature

def date_time_from_string(date_time: str) -> DateTime:
    return DateTime.fromisoformat(date_time.replace('Z', '+00:00'))

def get_epoch_time_in_seconds() -> int:
    return int(time.time())

def date_time_to_epoch_seconds(date_time: DateTime) -> int:
    return int(date_time.timestamp())