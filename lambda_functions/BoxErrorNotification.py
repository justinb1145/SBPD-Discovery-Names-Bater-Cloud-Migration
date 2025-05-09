import json
import logging
import boto3
import os
from botocore.exceptions import ClientError
from box_sdk_gen import BoxJWTAuth, BoxClient, JWTConfig

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Set up SES client
ses_client = boto3.client('ses')

# Set up AWS Secrets Manager client
secrets_client = boto3.client('secretsmanager')

source_email = os.environ.get('SOURCE_EMAIL')

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

def get_user_email(user_id):
    """Fetch the user's email address from Box using their user_id."""
    try:
        # Authenticate with Box
        jwt_config = get_box_config()
        auth = BoxJWTAuth(config=jwt_config)
        client = BoxClient(auth=auth)

        # Fetch user details
        user = client.users.get_user_by_id(user_id)
        logger.info(f"Fetched user details: {user}")

        # Return the user's email address
        return user.login
    except Exception as e:
        logger.error(f"Error fetching user email: {str(e)}")
        return None

def lambda_handler(event, context):
    try:
        logger.info(f"Received error event: {json.dumps(event)}")

        # Extract error details from the event
        file_name = event.get('file_name', 'Unknown File')
        error_reason = event.get('error_reason', 'Unknown Error')
        user_id = event.get('user_id')  # User ID of the user who uploaded the file
        file_link = event.get('file_link')  # File link from the payload

        if not user_id:
            logger.error("No user ID provided.")
            return {
                'statusCode': 400,
                'body': json.dumps('No user ID provided.')
            }

        # Fetch the user's email address
        user_email = get_user_email(user_id)
        if not user_email:
            logger.error(f"Unable to fetch email for user ID: {user_id}")
            return {
                'statusCode': 400,
                'body': json.dumps('Unable to fetch user email.')
            }

        # Construct email message
        subject = f"File Processing Failed: {file_name}"
        body_text = f"""
        DO NOT REPLY:

        The file '{file_name}' failed to process due to the following reason:
        {error_reason}

        You can access the file here: {file_link}

        Please review the file/folder and try again.
        """
        body_html = f"""
        <html>
            <body>
                <p>DO NOT REPLY:</p>
                <p>The file <strong>{file_name}</strong> failed to process due to the following reason:</p>
                <p><strong>{error_reason}</strong></p>
                <p>You can access the file <a href="{file_link}">here</a>.</p>
                <p>Please review the file/folder and try again.</p>
            </body>
        </html>
        """

        # Send email using SES with your verified sender email
        try:
            response = ses_client.send_email(
                Source=source_email,  # Enter verified sender email here as the source
                Destination={
                    'ToAddresses': [user_email]
                },
                Message={
                    'Subject': {'Data': subject},
                    'Body': {
                        'Text': {'Data': body_text},
                        'Html': {'Data': body_html}
                    }
                }
            )
            logger.info(f"Email sent successfully: {response['MessageId']}")
            return {
                'statusCode': 200,
                'body': json.dumps('Email notification sent successfully.')
            }
        # Handle case where email is unable to be sent
        except ClientError as e:
            logger.error(f"Failed to send email: {e.response['Error']['Message']}")
            return {
                'statusCode': 200,
                'body': json.dumps(f"Failed to send email: {e.response['Error']['Message']}")
            }
    except Exception as e:
        logger.error(f"Error in errorNotificationLambda: {str(e)}")
        return {
            'statusCode': 200,
            'body': json.dumps(f"Internal server error: {str(e)}")
        }
