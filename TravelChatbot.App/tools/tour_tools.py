import time
import boto3
from botocore.exceptions import ClientError
from config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
from models.tour import Tour
from models.user_tour import UserTour
from typing import List, Dict, Any, Optional
from tools.tour_search import embed_tours, search_tours

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
            Retrieve existing tours. Supports three modes:
            1. No parameters: returns all tours
            2. place parameter: queries tours for that specific location
            3. search_query parameter: performs semantic search based on the query
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
                },
                "search_query": {
                    "type": "string",
                    "description": (
                        "Natural language query for semantic search. Examples: "
                        "'tours in Hoi An', 'tours under 600000 VND', 'tourId abc123-xyz'"
                    )
                }
            },
            "required": []
        }
    } 
}

def get_tours(place: Optional[str] = None, search_query: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieve tours from the Tours DynamoDB table and optionally perform semantic search.
    If neither place nor search_query is provided, returns all tours.
    If place is provided, filters by that place.
    If search_query is provided, performs semantic search using ChromaDB.

    Args:
        place (Optional[str]): partition key to filter tours by place.
        search_query (Optional[str]): natural language query for semantic search.

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

        # After getting all tours, update the ChromaDB embeddings
        embed_tours(tours)

        # If there's a search query, use semantic search
        if search_query:
            return search_tours(search_query)

        return tours

    except ClientError as e:
        return [{"error": e.response["Error"]["Message"]}]
    

register_tour_function = {
    "type": "function",
    "function": {
        "name": "register_tour",
        "description": "Register a tour for a phone number. Requires tourId and phoneNumber.",
        "parameters": {
            "type": "object",
            "properties": {
                "tourId": {"type": "string"},
                "phoneNumber": {"type": "string"}
            },
            "required": ["tourId", "phoneNumber"]
        }
    }
}

def register_tour(tourId: str, phoneNumber: str) -> Dict[str, Any]:
    """
    Register a tour for a user.

    Steps:
    - Verify the tour exists by querying the Tours table using the tourId-index.
      If not found, raises ValueError("tour not found").
    - Check if the user already registered the tour in UserTours using tourId and phoneNumber
      as the table's partition/sort key combination. If found, raises ValueError("tour is registered").
    - If not registered, insert a new item into UserTours with tourId, phoneNumber, createAt (epoch),
      and startDate from the found tour.

    Returns:
        Dict with the created item on success.

    Raises:
        ValueError: for "tour not found" or "tour is registered".
        ClientError: for AWS errors.
    """
    dynamodb = boto3.client(
        "dynamodb",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )

    try:
        # 1) Find the tour by tourId using the tourId-index
        resp = dynamodb.query(
            TableName="Tours",
            IndexName="tourId-index",
            KeyConditionExpression="tourId = :t",
            ExpressionAttributeValues={":t": {"S": tourId}},
            Limit=1
        )
        items = resp.get("Items", [])
        if not items:
            raise ValueError("tour not found")

        tour_item = items[0]
        tour = Tour.from_dynamodb(tour_item)
        start_date = int(tour.startDate)

        # 2) Check if the tour is already registered for this phoneNumber
        resp_check = dynamodb.query(
            TableName="UserTours",
            KeyConditionExpression="tourId = :t AND phoneNumber = :p",
            ExpressionAttributeValues={
                ":t": {"S": tourId},
                ":p": {"S": phoneNumber}
            },
            Limit=1
        )
        if resp_check.get("Items"):
            raise ValueError("tour is registered")

        # 3) Register the tour
        created_at = int(time.time())
        dynamodb.put_item(
            TableName="UserTours",
            Item={
                "tourId": {"S": tourId},
                "phoneNumber": {"S": phoneNumber},
                "createAt": {"N": str(created_at)},
                "startDate": {"N": str(start_date)}
            }
        )

        return {
            "tourId": tourId,
            "phoneNumber": phoneNumber,
            "createAt": created_at,
            "startDate": start_date
        }

    except ClientError as e:
        return {"error": e.response["Error"]["Message"]}