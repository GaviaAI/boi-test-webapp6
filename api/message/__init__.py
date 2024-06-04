import logging
import os
import json
import requests
from datetime import datetime, timedelta
import pyodbc

import azure.functions as func

logging.basicConfig(level=logging.DEBUG)


search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
search_key = os.getenv("AZURE_SEARCH_API_KEY") 
search_api_version = '2023-07-01-Preview'
search_index_name = os.getenv("AZURE_SEARCH_INDEX")
#search_index_name=[]

AOAI_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
AOAI_key = os.getenv("AZURE_OPENAI_API_KEY")
AOAI_api_version = os.getenv("AZURE_OPENAI_API_VERSION")
embeddings_deployment = os.getenv("AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT")
chat_deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")

sql_db_server = os.getenv("SQL_DB_SERVER")
sql_db_user = os.getenv("SQL_DB_USER")
sql_db_password = os.getenv("SQL_DB_PASSWORD")
sql_db_name = os.getenv("SQL_DB_NAME")

blob_sas_url = os.getenv("BLOB_SAS_URL")

server_connection_string = f"Driver={{ODBC Driver 17 for SQL Server}};Server=tcp:{sql_db_server},1433;Uid={sql_db_user};Pwd={sql_db_password};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
database_connection_string = server_connection_string + f"Database={sql_db_name};"

# font color adjustments
blue, end_blue = '\033[36m', '\033[0m'

functions = [
    {
        "name": "get_boi_information",
        "description": "Find information about BOI based on a user question. Use only if the requested information if not already available in the conversation context.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_question": {
                    "type": "string",
                    "description": "User question (i.e., how much can i borrow?, etc.)"
                },
            },
            "required": ["user_question"],
        }
    }
]

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    messages = json.loads(req.get_body())

    response = chat_complete(messages, functions= functions, function_call= "auto")

    logging.info("the response is: %s", response)

    products = []
    
    try:
        response_message = response["choices"][0]["message"]     
    except:
        logging.info(response)
        
    # if the model wants to call a function
    if response_message.get("function_call"):
        logging.info("Response_message: %s", response_message)
        # Call the function. The JSON response may not always be valid so make sure to handle errors
        if "name" not in response_message["function_call"]:
            logging.error("Function name not found in response message.")
            return func.HttpResponse("Function name not found in response message.", status_code=500)

        # Extract the function name from the function call information
        function_call_info = response_message["function_call"]
        logging.info("Function call info: %s", function_call_info)

        if "name" not in function_call_info:
            logging.error("Function name not found in response message.")
            return func.HttpResponse("Function name not found in response message.", status_code=500)

        function_name = function_call_info.get("name").strip()
        logging.info("Extracted function name: %s", function_name)


        function_arguments = function_call_info.get("arguments", {})  # default to empty dict if not provided
        logging.info("FUNCTION NAME: %s", function_name)
        logging.info("FUNCTION ARGUMENTS: %s", function_arguments)
        # Log the response_message
        logging.info("Response message: %s", response_message)

        
        available_functions = {
            "get_boi_information": get_boi_information,
        }


        # Check if the function name exists in available_functions dictionary
        if function_name not in available_functions:
            logging.error("Function '%s' not found.", function_name)
            return func.HttpResponse(f"Function '{function_name}' not found.", status_code=500)

        # Retrieve the function from available_functions dictionary
        function_to_call = available_functions[function_name] 
        logging.info("Function to call: %s", function_to_call)

        # Load function arguments from response_message["function_call"]["arguments"]
        function_args = json.loads(response_message["function_call"]["arguments"])

        # Call the function with the loaded arguments
        function_response = function_to_call(**function_args)
        #print(function_name, function_args)
        logging.info("Function response: %s",function_response)

        # Add the assistant response and function response to the messages
        messages.append({
            "role": response_message["role"],
            "function_call": {
                "name": function_name,
                "arguments": response_message["function_call"]["arguments"],
            },
            "content": None
        })
        
        if function_to_call == get_boi_information:
            boi_info = json.loads(function_response)
            # Process BOI information and update function_response
            function_response = boi_info['content']

        messages.append({
            "role": "function",
            "name": function_name,
            "content": function_response,
        })
     
        response = chat_complete(messages, functions= functions, function_call= "none")
        
        response_message = response["choices"][0]["message"]

    messages.append({'role' : response_message['role'], 'content' : response_message['content']})

    logging.info(json.dumps(response_message))

    response_object = {
        "messages": messages,
        "products": products
    }

    return func.HttpResponse(
        json.dumps(response_object),
        status_code=200
    )
    
def generate_embeddings(text):
    """ Generate embeddings for an input string using embeddings API """

    url = f"{AOAI_endpoint}/openai/deployments/{embeddings_deployment}/embeddings?api-version={AOAI_api_version}"

    headers = {
        "Content-Type": "application/json",
        "api-key": AOAI_key,
    }

    data = {"input": text}

    response = requests.post(url, headers=headers, data=json.dumps(data)).json()
    return response['data'][0]['embedding']

############ BOI #############
def get_boi_information(user_question, top_k=1):
    """ Vectorize user query to search Cognitive Search vector search on index_name. Optional filter on categories field. """
    #logging.info('Helloooooo from get_boi_information function!')
    #for each index in 
    url = f"{search_endpoint}/indexes/{search_index_name}/docs/search?api-version={search_api_version}"

    headers = {
        "Content-Type": "application/json",
        "api-key": f"{search_key}",
    }
    
    vector = generate_embeddings(user_question)

    data = {
        "vectors": [
            {
                "value": vector,
                "fields": "contentVector",
                "k": top_k
            },
        ],
        "select": "title, content, url",
    }

    results = requests.post(url, headers=headers, data=json.dumps(data))    
    results_json = results.json()
    
    # Extracting the required fields from the results JSON
    boi_data = results_json['value'][0] # hard limit to top result for now

    response_data = {
        "title": boi_data.get('title'),
        "content": boi_data.get('content'),
        "url": boi_data.get('url'),
    }
    return json.dumps(response_data)
########## BOI #########################


def chat_complete(messages, functions, function_call='auto'):
    """  Return assistant chat response based on user query. Assumes existing list of messages """
    
    url = f"{AOAI_endpoint}/openai/deployments/{chat_deployment}/chat/completions?api-version={AOAI_api_version}"

    headers = {
        "Content-Type": "application/json",
        "api-key": AOAI_key
    }

    data = {
        "messages": messages,
        "functions": functions,
        "function_call": function_call,
        "temperature" : 0,
    }

    logging.info("THE DATA IS: %s", data)

    response = requests.post(url, headers=headers, data=json.dumps(data)).json()

    return response
