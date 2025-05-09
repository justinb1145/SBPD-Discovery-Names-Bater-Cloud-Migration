import json
import os
import logging
import boto3
from datetime import datetime
from box_sdk_gen import BoxJWTAuth, BoxClient, JWTConfig
from box_sdk_gen import SearchForContentType, SearchForContentContentTypes

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Get Error Lambda Function Name
error_lambda_function_name = os.environ.get('ERROR_LAMBDA')

# Set up AWS Lambda client
lambda_client = boto3.client('lambda')

# Set up AWS Secrets Manager client
secrets_client = boto3.client('secretsmanager')

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

def lambda_handler(event, context):
    try:
        logger.info("Starting Box file rename function.")
        logger.info(f"Received event: {json.dumps(event)}")

        # Extract required parameters
        file_id = event.get('file_id')
        new_file_name = event.get('new_file_name')
        user_id = event.get('user_id')
        pd_case_number = event.get('pdCaseNumber')

        
        # Validate that all required fields are present
        if not file_id or not new_file_name or not user_id or not pd_case_number:
            missing_fields = [key for key in ['file_id', 'new_file_name', 'user_id', 'pdCaseNumber'] if key not in event]
            logger.error(f"Missing required data: {missing_fields}")
            return {
                'statusCode': 200,
                'body': json.dumps({'error': f"Missing required fields: {', '.join(missing_fields)}"})
            }

        # Validate pdCaseNumber format (PDYYXXXXX)
        if not pd_case_number.startswith("PD") or len(pd_case_number) != 9 or not pd_case_number[2:4].isdigit():
            logger.error(f"Invalid pdCaseNumber format: {pd_case_number}")
            return {
                'statusCode': 200,
                'body': json.dumps({'error': "Invalid pdCaseNumber format. Expected format: 'pdYYxxxx' (e.g., 'pd25xxxx')."})
            }

        year_suffix = pd_case_number[2:4]
        year = int(f"20{year_suffix}")
        current_year = datetime.now().year

        # Authenticate with Box
        jwt_config = get_box_config()
        auth = BoxJWTAuth(config=jwt_config)
        client = BoxClient(auth=auth)
        user_client = client.with_as_user_header(user_id=user_id)

        # First, rename the file immediately
        logger.info(f"Renaming file '{file_id}' to '{new_file_name}'")
        renamed_file = user_client.files.update_file_by_id(
            file_id,
            name=new_file_name,
        )
        logger.info(f"Successfully renamed file: {renamed_file.name}")

        # Try to locate the Discovery folder to move the file
        e_defender_query = "eDefender" if year == current_year else f"eDefender_{year}"
        logger.info(f"Searching for 'eDefender' folder: {e_defender_query}")

        # Use search query to look for eDefender folder
        e_defender_folder_search = user_client.search.search_for_content(
            query=e_defender_query,
            type=SearchForContentType.FOLDER,
            content_types=[SearchForContentContentTypes.NAME],
            fields=["id", "name"],
        )

        if not e_defender_folder_search.entries:
            raise Exception(f"'{e_defender_query}' folder not found.")

        e_defender_folder_id = e_defender_folder_search.entries[0].id

        logger.info(f"Searching for case folder '{pd_case_number}'")
        case_folder_search = user_client.search.search_for_content(
            query=pd_case_number,
            type=SearchForContentType.FOLDER,
            content_types=[SearchForContentContentTypes.NAME],
            ancestor_folder_ids=e_defender_folder_id,
            fields=["id", "name"],
        )

        if not case_folder_search.entries:
            raise Exception(f"Case folder '{pd_case_number}' not found inside '{e_defender_query}'.")

        if len(case_folder_search.entries) > 1:
            raise Exception(f"Multiple folders found for case number: {pd_case_number}")

        case_folder_id = case_folder_search.entries[0].id

        logger.info(f"Searching for 'Discovery' folder inside case folder '{pd_case_number}'")
        discovery_folder_search = user_client.search.search_for_content(
            query="Discovery",
            type=SearchForContentType.FOLDER,
            content_types=[SearchForContentContentTypes.NAME],
            ancestor_folder_ids=case_folder_id,
            fields=["id", "name"],
        )

        if not discovery_folder_search.entries:
            raise Exception(f"'Discovery' folder not found inside '{pd_case_number}'.")

        discovery_folder_id = discovery_folder_search.entries[0].id

        # File was already renamed, now move it
        logger.info(f"Moving file '{renamed_file.name}' to 'Discovery' folder.")
        moved_file = user_client.files.update_file_by_id(
            file_id,
            parent={"id": discovery_folder_id}
        )

        logger.info(f"File moved to Discovery folder ID: {discovery_folder_id}")
        
        #This checks if there have been any soft errors from previous lambda's
        if event.get("error"):
            logger.info("Triggering error Lambda due to external event error.")
            external_error_payload = {
                'file_name': new_file_name,
                'error_reason': event['error'],
                'user_id': user_id,
                'file_link': f"https://app.box.com/file/{file_id}"
            }
            lambda_client.invoke(
                FunctionName=error_lambda_function_name,
                InvocationType='Event',
                Payload=json.dumps(external_error_payload)
            )
            
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f"File renamed to '{renamed_file.name}' and moved to folder '{pd_case_number}'",
                'file_id': file_id,
                'folder_id': discovery_folder_id,
            })
        }

    except Exception as e:
        logger.error(f"Error during file processing: {str(e)}")
        error_payload = {
            'file_name': new_file_name,
            'error_reason': str(e),
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
            'body': json.dumps({'message': f"File renamed to '{new_file_name}', but could not be moved.", 'error': str(e)})
        }
