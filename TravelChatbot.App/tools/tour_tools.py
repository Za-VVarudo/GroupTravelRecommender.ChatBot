import boto3
from botocore.exceptions import ClientError
from config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
from models.user_tour import UserTour
from typing import List, Dict, Any

get_registered_tours_function = {
    "type": "function",
    "function": {
        "name": "get_registered_tours",
        "description": "Retrieve all registered tours for a given phone number",
        "parameters": {
            "type": "object",
            "properties": {"phoneNumber": {"type": "string"}},
            "required": ["phoneNumber"]
        }
    }
}

def get_registered_tours(phoneNumber: str) -> List[Dict[str, Any]]:
    """
    Retrieve all registered tours for a given phone number

    Args:
        phoneNumber (str): The user's phone number.

    Returns:
        List[Dict[str, Any]]: A list of tours (each as a dict).
    """
    dynamodb = boto3.client(
        "dynamodb",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )

    try:
        response = dynamodb.query(
            TableName="UserTours",
            IndexName="phoneNumber-createAt-index",
            KeyConditionExpression="phoneNumber = :p",
            ExpressionAttributeValues={":p": {"S": phoneNumber}},
        )

        items = response.get("Items", [])
        tours = [UserTour.from_dynamodb(item).to_dict() for item in items]
        return tours

    except ClientError as e:
        return [{"error": e.response["Error"]["Message"]}]