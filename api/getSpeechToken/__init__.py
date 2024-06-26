import logging
import requests
import os

import azure.functions as func

# Define subscription key and region
#subscription_key = os.getenv("AZURE_SPEECH_API_KEY")
subscription_key="08a7b4eb34db40bba181cbabc4df4e4a"
#region = os.getenv("AZURE_SPEECH_REGION")
region="westeurope"


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    # Define token endpoint
    #token_endpoint = f"https://{region}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
    token_endpoint = f"https://westeurope.api.cognitive.microsoft.com/sts/v1.0/issueToken"

    # Make HTTP request with subscription key as header
    response = requests.post(token_endpoint, headers={"Ocp-Apim-Subscription-Key": subscription_key})

    if response.status_code == 200:
        access_token = response.text
        return func.HttpResponse(
             access_token,
             status_code=200
        )
    else:
        return func.HttpResponse(response.status_code)
