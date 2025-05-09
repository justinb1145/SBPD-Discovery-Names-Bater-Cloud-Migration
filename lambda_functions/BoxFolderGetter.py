import json
import os
import logging
import boto3
from box_sdk_gen import BoxJWTAuth, BoxClient, JWTConfig

# set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Set up AWS Secrets Manager client
secrets_client = boto3.client('secretsmanager')

# Get Next Lambda Function Name
target_lambda_function_name = os.environ.get('NEXT_LAMBDA')

# Get Error Lambda Function Name
error_lambda_function_name = os.environ.get('ERROR_LAMBDA')

def get_box_config():
    """Load the JWT configuration for Box authentication from AWS Secrets Manager."""
    # Retrieve the secret from AWS Secrets Manager
    secret_name = os.environ.get('BOX_SECRET_NAME')
    if not secret_name:
      raise ValueError("BOX_SECRET_NAME environment variable is not set.")
      
    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)

        # Parse the secret JSON
        secret_data = json.loads(response['SecretString'])  # Convert JSON string to dictionary

        # Extract Box credentials from the stored JSON structure
        box_settings = secret_data["boxAppSettings"]
        app_auth = box_settings["appAuth"]

        # Create JWTConfig using retrieved credentials
        config = JWTConfig(
            client_id=box_settings["clientID"],
            client_secret=box_settings["clientSecret"],
            jwt_key_id=app_auth["publicKeyID"],
            private_key=app_auth["privateKey"].replace("\\n", "\n"),
            private_key_passphrase=app_auth["passphrase"],
            enterprise_id=secret_data["enterpriseID"]
        )

        logger.info("JWTConfig successfully loaded from AWS Secrets Manager.")
        return config

    except Exception as e:
        logger.error(f"Error loading JWTConfig from Secrets Manager: {str(e)}")
        raise

# Set up AWS Lambda client for invoking another Lambda function
lambda_client = boto3.client('lambda')

# Lambda handler to test Box SDK
def lambda_handler(event, context):
    try:
        logger.info("Starting Box SDK test function.")
        # Log the received event for debugging
        logger.info(f"Received event: {json.dumps(event)}")

        # Load the Box configuration
        jwt_config = get_box_config()

        # Authenticate with Box
        auth = BoxJWTAuth(config=jwt_config)
        client = BoxClient(auth=auth)
        logger.info("Successfully authenticated with Box.")

        # Fetch a test folder to confirm functionality/ we can replace it later on with an actual folder id
        folder_id = event.get('parent_folder_id')
        user_id = event.get('user_id')  # Add user_id to the event payload

        if not folder_id:
            logger.error("Missing required data: folder_id")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing parent folder ID'})
            }
        
        if not user_id:
            logger.error("Missing required data: user_id")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing user ID'})
            }

        user_client = client.with_as_user_header(user_id=user_id)

        logger.info(f"Fetching folder details for Folder ID: {folder_id}")
        folder = user_client.folders.get_folder_by_id(folder_id, fields=["name"])

        # Log and return the folder name using the 'name' attribute
        folder_name = folder.name
        logger.info(f"Fetched folder: {folder_name}")
        
        event["folder_name"] = folder_name 
        logger.info(f"Updated event: {event}")

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
                FunctionName=error_lambda_function_name,
                InvocationType='Event',
                Payload=json.dumps(error_payload))
            return {
                'statusCode': 200,
                'body': json.dumps(f'Error invoking target Lambda function: {str(e)}')
            }

    except Exception as e:
        logger.error(f"Error during Box SDK test: {str(e)}")
        return {
            'statusCode': 200,
            'body': json.dumps(f"Internal server error: {str(e)}")
        }
