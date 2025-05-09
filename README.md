# SBPD-NamesBater-Cloud-Migration
# Table of Contents

1. [Summary](#summary)
2. [Features](#features)
3. [Requirements](#requirements)
4. [Dependencies](#dependencies)
5. [Setup AWS Side](#setup-aws-side)
6. [Create the Lambda Functions](#create-the-lambda-functions)
   1. [BoxInputFunction Setup](#boxinputfunction-setup)
   2. [BoxFolderGetter Setup](#boxfoldergetter-setup)
   3. [DiscoveryBatesNamer Setup](#discoverybatesnamer-setup)
   4. [BoxFileUpdater Setup](#boxfileupdater-setup)
   5. [BoxErrorNotification Setup](#boxerrornotification-setup)
7. [Box Side Setup](#box-side-setup)
   1. [Steps for Setting Up Box Skills Folder](#steps-for-setting-up-box-skills-folder)
8. [User Guide](#user-guide)
9. [How It Works](#how-it-works)

---
## Summary:
This AWS-based application parses discovery PDF files uploaded to Box, extracts Bates numbers, renames the files in Box, and moves them to the appropriate discovery folder. It leverages AWS Lambda, the Box API, and PDF parsing libraries to automate the process of organizing discovery documents.

### Features:
- PDF Parsing: Extracts Bates numbers from discovery PDF files.
- Box Integration: Renames and moves files directly within Box based on parsed data.
- AWS Lambda: The process is handled within a Lambda function for scalable and cost-efficient processing.
- Security: Uses AWS Secrets Manager for credential management and Box API for webhook authentication.

### Requirements:
- AWS Account: Ensure your AWS Lambda function is configured and linked with the necessary IAM roles.
- Box Developer Account: Set up an application in the Box Developer Console to obtain your client ID, secret,

### Dependencies:
- boxsdkgen (for interacting with Box API)
- PyMuPDF (for PDF parsing)
- requests (for making HTTP requests)

---
## Setup AWS Side
Before we create our Lambda functions, let's create the necessary layers for the dependencies:
1. **BoxSDKGen**
2. **PyMuPDF**
3. **Requests**

### Steps to create Lambda Layers:
1. **Download the Lambda layer zips**:
   - Go ahead and download the 3 zip files located in the `lambda_layers` folder.

2. **Create the Lambda Layers in AWS**:
   - Log in to AWS
   - Go to the AWS Lambda Menu
   - In the left-hand menu, select **Layers** under the **Additional Resources** section.
   - Click on **Create layer**.

3. **Creating a Lambda Layer**:
   - **Name your Layer** (e.g., BoxSDKGen, PyMuPDF, or Requests).
   - **Upload the zip file** for each dependency:
     - For **BoxSDKGen**, upload the corresponding zip from your `lambda_layers` folder.
     - Repeat for **PyMuPDF** and **Requests**.
   - For each layer:
     - Set the **compatible runtimes** to **Python 3.11** 
   - Click **Create** to finish the process.

---
Next, we'll set up our Box credentials in AWS Secrets Manager so they can be securely accessed by the Lambda function at runtime.

### Steps to set-up AWS Secrets Manager:

1. **Go to the AWS Console**  
   Navigate to the [AWS Secrets Manager] console.

2. **Click "Store a new secret"**

3. **Select "Other type of secret"**

4. **Add your Box JWT Config as a raw JSON Config**  
   - Select the Plaintext option and fill it in like below
   Example:
     ```json
     {
      "boxSkillSettings":{
         "primaryKey":"your_box_skill_primary_key",
         "secondaryKey":"your_box_skill_secondary_key"
         },
      "boxAppSettings": {
         "clientID": "your_box_app_client_id",
         "clientSecret": "your_box_app_client_secret",
         "appAuth": {
            "publicKeyID": "your_box_app_public_key_id",
            "privateKey": "your_box_app_private_key_id",
            "passphrase": "your_box_app_passphrase"
            }
         },
         "enterpriseID": "your_box_enterprise_id"
      }

     ```

5. **Name your secret**  
   For Example `box_credentials`.

6. **Attach permissions**  
   Ensure that your Lambda function’s IAM role has permissions to access this secret.  
   You’ll need to add the following permissions to the Lambda role:
   - `SecretsManagerReadWrite`

---
Next we will Discuss on how to make the lambda functions

### Create the following Lambda Functions:
1. **BoxInputFunction**
2. **BoxFolderGetter**
3. **DiscoveryBatesNamer**
4. **BoxFileUpdater**

### General Setup for all Lambda Functions
1. Navigate to the AWS Lambda console and create a new Lambda function.
2. Select **Python 3.11** as the runtime.
3. Choose **x86_64** as the architecture.
4. Assign an IAM role to the Lambda function that includes the following permissions:
    - `AWSLambda_FullAccess`
    - `AWSLambdaBasicExecutionRole`
    - (Make sure the IAM role has these permissions.)


Next, we will go over the specific setups for each Lambda function.

---
### BoxInputFunction Setup
#### Set Up the Lambda Function:
1. In the **AWS Lambda Console**, create a new Lambda function called **BoxInputFunction**.
2. Select **Python 3.11** as the runtime.
3. Choose **x86_64** as the architecture.
4. In the **Function code** section, paste the code from `BoxInputFunction.py` in the `lambda_functions` folder of the Repo.

#### General Configuration
Ensure the following general configuration settings are applied:
1. **Memory**: Set to **128 MB**  
2. **Ephemeral Storage**: Set to **512 MB**  
3. **Timeout**: Set to **3 minute (3 min 0 sec)**  
4. **SnapStart**: Set to **None**  

#### Create API Gateway for BoxInputFunction:
1. Navigate to the **API Gateway Console**.
2. Click on **Create API** and choose **HTTP API**.
3. Set **Authorization** to **NONE**.
4. Set the **API name** (e.g., `BoxInputFunctionAPI`).
5. Click **Create API**.
6. Save the **API endpoint URL** once it's created.
   
#### Set Environment Variable:
1. In the **Environment variables** section of the Lambda function, add the following key-value pair:
    - **Key**: `NEXT_LAMBDA`
    - **Value**: `BoxFolderGetter`
    - **Key**: `ERROR_LAMBDA`
    - **Value**: `BoxErrorNotification`
    - **Key**: `BOX_SECRET_NAME`
    - **Value**: `box_credentials`

#### Attach the Lambda Layer:
1. This Lambda Function doesn't require any additional layers

### BoxFolderGetter Setup
#### Set Up the Lambda Function:
1. In the **AWS Lambda Console**, create a new Lambda function called **BoxInputFunction**.
2. Select **Python 3.11** as the runtime.
3. Choose **x86_64** as the architecture.
4. In the **Function code** section, paste the code from `BoxFolderGetter.py` in the `lambda_functions` folder of the Repo.

#### General Configuration
Ensure the following general configuration settings are applied:
1. **Memory**: Set to **128 MB**  
2. **Ephemeral Storage**: Set to **512 MB**  
3. **Timeout**: Set to **3 minute (3 min 0 sec)**  
4. **SnapStart**: Set to **None**  

#### Set Environment Variable:
1. In the **Environment variables** section of the Lambda function, add the following key-value pair:
    - **Key**: `NEXT_LAMBDA`
    - **Value**: `DiscoveryBatesNamer`
    - **Key**: `ERROR_LAMBDA`
    - **Value**: `BoxErrorNotification`
    - **Key**: `BOX_SECRET_NAME`
    - **Value**: `box_credentials`
      
#### Attach the Lambda Layer:
1. In the **Layers** section of the Lambda function, click **Add a layer* and the following.
    - Choose the **BoxSDKGen** layer

### DiscoveryBatesNamer Setup
#### Set Up the Lambda Function:
1. In the **AWS Lambda Console**, create a new Lambda function called **DiscoveryBatesNamer**.
2. Select **Python 3.11** as the runtime.
3. Choose **x86_64** as the architecture.
4. In the **Function code** section, paste the code from `DiscoveryBatesNamer.py` in the `lambda_functions` folder of the Repo.

#### General Configuration
Ensure the following general configuration settings are applied:
1. **Memory**: Set to **128 MB**  
2. **Ephemeral Storage**: Set to **512 MB**  
3. **Timeout**: Set to **3 minute (3 min 0 sec)**  
4. **SnapStart**: Set to **None**  

#### Set Environment Variable:
1. In the **Environment variables** section of the Lambda function, add the following key-value pair:
    - **Key**: `NEXT_LAMBDA`
    - **Value**: `BoxFileUpdater`
    - **Key**: `ERROR_LAMBDA`
    - **Value**: `BoxErrorNotification`

#### Attach the Lambda Layers:
1. In the **Layers** section of the Lambda function, click **Add a layer** and select the following:
    - **Requests**
    - **PyMuPDF**

### BoxFileUpdater Setup
#### Set Up the Lambda Function:
1. In the **AWS Lambda Console**, create a new Lambda function called **BoxFileUpdater**.
2. Select **Python 3.11** as the runtime.
3. Choose **x86_64** as the architecture.
4. In the **Function code** section, paste the code from `BoxFileUpdater.py` in the `lambda_functions` folder of the Repo.

#### General Configuration
Ensure the following general configuration settings are applied:
1. **Memory**: Set to **128 MB**  
2. **Ephemeral Storage**: Set to **512 MB**  
3. **Timeout**: Set to **3 minute (3 min 0 sec)**  
4. **SnapStart**: Set to **None**  

#### Set Environment Variables:
1. In the **Environment variables** section of the Lambda function, add the following key-value pairs:
    - **Key**: `ERROR_LAMBDA`
    - **Value**: `BoxErrorNotification`
    - **Key**: `BOX_SECRET_NAME`
    - **Value**: `box_credentials`

#### Attach the Lambda Layer:
1. In the **Layers** section of the Lambda function, click **Add a layer* and the following.
    - Choose the **BoxSDKGen** layer

### BoxErrorNotification Setup
#### Set up the Lambda Function:
1. In the **AWS Lambda Console**, create a new Lambda function called **BoxErrorNotification**.
2. Select **Python 3.11** as the runtime.
3. Choose **x86_64** as the architecture.
4. In the **Function code** section, paste the code from `BoxErrorNotification.py` in the `lambda_functions` folder of the Repo.
5. You need to create a verified instance of your email in order to receive and send emails. This is done by accessing Amazon Simple Email Service.
6. Once you are in AWS SES, on the left-hand side bar, click on *Identities* under Configuration
7. Click on *Create Identity*, select *Email address*, enter a valid email address and then click on *Create Identity* at the bottom
8. You will be prompted with an email verification link via email and once you verify the email address, you will be able to use AWS SES
### EMAIL VERIFICATION IS ONLY REQUIRED ONCE

#### General Configuration
Ensure the following general configuration settings are applied:
1. **Memory**: Set to **128 MB**  
2. **Ephemeral Storage**: Set to **512 MB**  
3. **Timeout**: Set to **3 minute (3 min 0 sec)**  
4. **SnapStart**: Set to **None**

#### Set Environment Variables:
1. In the **Environment variables** section of the Lambda function, add the following key-value pairs:
    - **Key**: `BOX_SECRET_NAME`
    - **Value**: `box_credentials`
    - **Key**: `SOURCE_EMAIL`
    - **Value**: `Your_Source_Email`

#### Attach the Lambda Layer:
1. In the **Layers** section of the Lambda function, click **Add a layer* and the following.
    - **BoxSDKGen** layer
    - **Requests** layer
#### EXTRA INFORMATION ABOUT BoxErrorNotification FUNCTION:
#### Once the current pipeline is out of testing and ready to go into production, you can request for permission to 
#### exit of out SES Sandbox mode and not have to verify every email address that wants to receive/send emails
---
## Box Side Setup
Now that we've completed the AWS Lambda setup, let's move on to the **Box side** configuration. This involves setting up a **Box Custom Skill** and configuring it to process PDF files with our Lambda functions.

### Steps for Setting Up Box Skills Folder:
1. **Create a Box Developer Account** (if you don't have one already):
   - Go to [Box Developer Console](https://account.box.com/login) and sign in or create a new account.

2. **Create a Custom Skill**:
   - Navigate to the **Box Developer Console**.
   - Under the **Custom Skills** section, click **Create New Custom Skill**.
   - Choose **Custom Skill** and name it (e.g., `DiscoveryProcessorSkill`).

3. **Configure the Custom Skill**:
   - In the **Configuration** settings of your new skill, locate the **File Extensions** field.
   - Enter `.pdf` as the file extension to ensure that only PDF files are processed by this skill.
   - Set the **Invocation URL** to the **API endpoint URL** of your **BoxInputFunction** Lambda function. This is the URL you obtained after creating the API Gateway for the `BoxInputFunction`.

4. **Enable the Skill**:
   - After setting the file extension and invocation URL, enable the skill for use in your Box environment.

This setup connects Box with your Lambda functions, ensuring that PDF files are properly processed when uploaded to Box.

---
## User Guide

### Upload the Folder Containing the Discovery Files
- Ensure that the folder you're uploading contains all the discovery PDF files that need to be processed.  
- The folder **must** be uploaded to the **Skills Applied Folder** in Box, where the custom skill is applied.  

### Name the Folder Following This Format:
- The folder name **must** follow this format:  `PDCase#_Disc#`
- **Example:** `PD251234_02`
    - **PD251234** refers to the **case number**, and the **first two digits** of `PD` indicate the **year** of the files.  
        - Example: `PD251234` means files from the **year 2025**.  
    - **02** refers to the **discovery disc number** (in this example, **disc number 2**).  


Once the folder is uploaded with the correct naming convention to the Skills Applied Folder in Box, the application will automatically begin processing the files.

---
## How It Works

Once the folder is uploaded to the **Skills Applied Folder** in Box, the application processes each individual file as it is uploaded:

1. **Box Detects Each Uploaded File**  
   - Each time a PDF file is uploaded to the folder, the Box custom skill triggers the processing pipeline.  

2. **BoxInputFunction Captures File Details**  
   - The `BoxInputFunction` Lambda function is invoked for each file.  
   - It extracts key information from the event payload:  
     - `access_token` – Authentication token for Box API.  
     - `file_id` – Unique ID of the uploaded file.  
     - `original_file_name` – The name of the file before processing.  
     - `parent_folder_id` – The ID of the uploaded folder.  
     - `user_id` – The ID of the user who uploaded the file.  
   - This information is then structured into a **custom payload** and passed to the next function.

3. **BoxFolderGetter Identifies the folder name**   
   - It uses **JWT authentication** from `box_sdk_gen` to authenticate with Box and obtain the **folder name** where the file is stored.  
   - The folder name is then added to the custom payload before passing it to the next step.

4. **DiscoveryBatesNamer Extracts Bates and Renames Files**
   - Detect and extract **Bates numbers** from the file.
        - Detects bates of the following format `// 00000`
   - Steps performed:
     1. Downloads the PDF file from Box.
     2. Scans the **bottom portion** of each page for Bates stamps.
     3. Validates if the extracted Bates numbers are **consecutive** and match the total page count.
     4. Formats a new file name using the extracted **Bates range, disc number, and original filename**:
     5. Updates the payload with the **pdCaseNumber** and **new file name**.
     6. Forwards the updated event to the next Lambda function for further processing.

5. **BoxFileUpdater Renames and Moves Files**  
   - The file is renamed in box.  
   - It is then moved to the appropriate **Discovery Folder** in Box based on its PD case number and year.

6. **BoxErrorNotification Handles Error Cases of File Processes/Missing or Duplicate PD Case Folders**
   - **Handles case error where**:
      1. Missing Bate Stamps
      2. Inconsecutive Bate Stamps
      3. Duplicate PD Case Folders
      4. Dicovery Folder not found in PD Case Folder
      5. File size is bigger than 64 MB
      6. Error in invoking following lambda functions

### Summary  
As each discovery file is uploaded, the system **automatically processes, renames, and moves it** to the correct location—ensuring a smooth and organized workflow without any manual intervention. In the case where a file is unable to be processed or a PD Case folder is missing, the system sends out an email notification alerting the user for reason of error and a link to view the file. 
