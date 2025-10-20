import boto3
from botocore.exceptions import ClientError
from config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
from models.tour import Tour
from models.user_tour import UserTour
from typing import List, Dict, Any, Optional

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


get_tours_function = {
    "type": "function",
    "function": {
        "name": "get_tours",
        "description": """
            Retrieve existing tours. If a 'place' is provided, it queries tours for that location.
            Returns a list of tours as dictionaries."""
        ,
        "parameters": {
            "type": "object",
            "properties": {
                "place": {
                    "type": "string",
                    "description": (
                        "The name of the place in Vietnam to filter tours by. "
                        "If omitted, returns all available tours."
                    )
                }
            },
            "required": []
        }
    } 
}

def get_tours(place: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieve tours from the Tours DynamoDB table and map them to the Tour model.
    If `place` is provided, query by partition key `place`; otherwise scan the table.

    Args:
        place (Optional[str]): partition key to filter tours by place.

    Returns:
        List[Dict[str, Any]]: A list of tours as dictionaries, or a list with an error dict on failure.
    """
    dynamodb = boto3.client(
        "dynamodb",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )

    try:
        tours: List[Dict[str, Any]] = []

        if place:
            response = dynamodb.query(
                TableName="Tours",
                KeyConditionExpression="place = :p",
                ExpressionAttributeValues={":p": {"S": place}},
            )
            items = response.get("Items", [])
            tours.extend([Tour.from_dynamodb(item).to_dict() for item in items])

            while "LastEvaluatedKey" in response:
                response = dynamodb.query(
                    TableName="Tours",
                    KeyConditionExpression="place = :p",
                    ExpressionAttributeValues={":p": {"S": place}},
                    ExclusiveStartKey=response["LastEvaluatedKey"]
                )
                items = response.get("Items", [])
                tours.extend([Tour.from_dynamodb(item).to_dict() for item in items])

        else:
            response = dynamodb.scan(TableName="Tours")
            items = response.get("Items", [])
            tours.extend([Tour.from_dynamodb(item).to_dict() for item in items])

            while "LastEvaluatedKey" in response:
                response = dynamodb.scan(
                    TableName="Tours",
                    ExclusiveStartKey=response["LastEvaluatedKey"]
                )
                items = response.get("Items", [])
                tours.extend([Tour.from_dynamodb(item).to_dict() for item in items])

        return tours

    except ClientError as e:
        return [{"error": e.response["Error"]["Message"]}]