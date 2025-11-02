import time
import boto3
from botocore.exceptions import ClientError
from config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, HERITAGE_GUIDE_S3_BUCKET
from models.tour import Tour
from models.user_tour import UserTour
from typing import List, Dict, Any, Optional
from tools.tour_search import (
    embed_tours,
    search_tours,
    embed_pdf_chunks,
    search_tour_heritage,
    heritage_chunk_exists,
)
from utilities.pdf_reader import chunk_text, extract_text_from_pdf_bytes
from utilities.s3_utils import download_s3_object

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


get_heritage_guide_function = {
    "type": "function",
    "function": {
        "name": "get_heritage_guide",
        "description": """
            Retrieve heritage guide information for a specific place. 
            Returns detailed cultural and historical information from available heritage guides.""",
        "parameters": {
            "type": "object",
            "properties": {
                "place": {
                    "type": "string",
                    "description": "The name of the place in Vietnam to get heritage guide information for."
                },
                "search_query": {
                    "type": "string",
                    "description": "Optional natural language query to search within heritage guides. Examples: 'Hue's tourist information', 'Hue's heritage sites', 'Places to visit in Hue'..."
                },
                "pagination_token": {
                    "type": "string",
                    "description": "Token for getting the next page of results. Omit for first page."
                },
                "page_size": {
                    "type": "integer",
                    "description": "Number of results to return per page. Always return 3 if user is not specified. Maximum is 5.",
                    "default": 3
                }
            },
            "required": ["place"]
        }
    }
}

get_tours_function = {
    "type": "function",
    "function": {
        "name": "get_tours",
        "description": """
            Retrieve existing tours with pagination support. Supports three modes:
            1. No parameters: returns all tours
            2. place parameter: queries tours for that specific location
            3. search_query parameter: performs semantic search based on the query
            Returns paginated results with a next page token.""",
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
                },
                "pagination_token": {
                    "type": "string",
                    "description": "Token for getting the next page of results. Omit for first page."
                },
                "page_size": {
                    "type": "integer",
                    "description": "Number of results to return per page. Default is 10.",
                    "default": 10
                }
            },
            "required": []
        }
    } 
}

def get_tours(
    place: Optional[str] = None, 
    search_query: Optional[str] = None, 
    type: Optional[str] = None,
    pagination_token: Optional[str] = None,
    page_size: int = 10
) -> Dict[str, Any]:
    """
    Retrieve tours from the Tours DynamoDB table and optionally perform semantic search with pagination.
    If neither place nor search_query is provided, returns all tours.
    If place is provided, filters by that place.
    If search_query is provided, performs semantic search using Pinecone.

    Args:
        place (Optional[str]): partition key to filter tours by place.
        search_query (Optional[str]): natural language query for semantic search.
        type (Optional[str]): filter by document type.
        pagination_token (Optional[str]): token for getting the next page of results
        page_size (int): number of results per page, default is 10

    Returns:
        Dict[str, Any]: Dictionary containing:
            - results: List of tours as dictionaries
            - next_token: Token for getting the next page (None if no more results)
            - error: Error message if any
    """
    # If there's a search query, go directly to semantic search
    if search_query:
        return search_tours(
            query=search_query,
            type="tour_info",
            place=place,  # Pass the place parameter for filtering
            pagination_token=pagination_token,
            page_size=page_size
        )

    # For non-search queries, use DynamoDB pagination
    dynamodb = boto3.client(
        "dynamodb",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )

    try:
        # Build the base query parameters
        query_params = {
            "TableName": "Tours",
            "Limit": page_size
        }

        # Add pagination token if provided
        if pagination_token:
            query_params["ExclusiveStartKey"] = {"S": pagination_token}

        # Add place filter if provided
        if place:
            query_params.update({
                "KeyConditionExpression": "place = :p",
                "ExpressionAttributeValues": {":p": {"S": place}}
            })
            response = dynamodb.query(**query_params)
        else:
            response = dynamodb.scan(**query_params)

        # Convert items to tour dictionaries
        items = response.get("Items", [])
        tours = [Tour.from_dynamodb(item).to_dict() for item in items]

        return {
            "results": tours,
            "next_token": None
        }

    except ClientError as e:
        return {
            "results": [],
            "next_token": None,
            "error": e.response["Error"]["Message"]
        }


def get_heritage_guide(
    place: str,
    search_query: Optional[str] = None,
    pagination_token: Optional[str] = None,
    page_size: int = 10
) -> Dict[str, Any]:
    """
    Retrieve heritage guide information for a specific place.

    Args:
        place (str): The name of the place to get heritage guide information for.
        search_query (Optional[str]): Optional natural language query to search within heritage guides. Examples: "Hue's tourist information", "Hue's heritage sites", "Tour herigate guide in Hue",...
        pagination_token (Optional[str]): Token for getting the next page of results
        page_size (int): Number of results per page, default is 10

    Returns:
        Dict[str, Any]: Dictionary containing:
            - results: List of heritage guides
            - next_token: Token for getting the next page (None if no more results)
            - error: Error message if any
    """
    result = {
        "results": [],
        "next_token": None
    }

    try:
        if search_query is None:
            search_query = f"top 5 sites to visit in {place}"
        # 1) Use `search_tours` to find tour metadata for this place (prefer vector index)
        tour_search_results = search_tours(query=search_query, place=place, type="tour_info", page_size=1)
        tours_metadata = tour_search_results.get("results", [])

        # If no tours found via vector search return not found heritage guides
        if not tours_metadata:
            return result

        # 2) For each tour metadata, check whether the first chunk exists in the heritage index.
        #    If any tour has existing chunk(s), we'll query the heritage index normally.
        existingTour = None
        for meta in tours_metadata:
            if meta.get("place").casefold() == place.casefold():
                existingTour = meta
                break

        if existingTour is None:
            return result

        tourId = existingTour["tourId"]
        # 3) If we have existing chunks in Pinecone, query heritage index directly
        if existingTour is not None and heritage_chunk_exists(chunk_id = f"{tourId}_heritageGuide_0"):
            place_query = f"{search_query} in {place}" if search_query else place
            search_results = search_tour_heritage(
                query=place_query,
                place=place,
                pagination_token=pagination_token,
                page_size=page_size,
            )

            # Filter (defensive) and return
            results = [r for r in search_results.get("results", []) if r.get("place") == place]
            next_token = search_results.get("next_token") if len(results) >= page_size else None
            return {"results": results, "next_token": next_token}

        heritageGuide = existingTour.get("heritageGuide")
        print("Not existing embeded data, fetching heritage guide S3 key:", heritageGuide)
        if not heritageGuide:
            return {
                "results": [],
                "next_token": None
            }
        
        try:
            s3_client = boto3.client("s3",
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_REGION,
            )
            pdf = download_s3_object(HERITAGE_GUIDE_S3_BUCKET, heritageGuide, s3_client)
            if pdf.get("body"):
                text = extract_text_from_pdf_bytes(pdf["body"])
                if text:
                    chunks = chunk_text(text, chunk_size=2000, overlap=200)
                    if chunks:
                        try:
                            embed_pdf_chunks(chunks, existingTour)
                        except Exception as e:
                            print(f"Error embedding chunks for tour {tourId}: {str(e)}")
        except Exception as e:
            print(f"Error fetching/embedding heritage guide for tour {tourId}: {str(e)}")

        # After embedding, query the heritage index for this place
        place_query = f"{search_query} in {place}" if search_query else place
        search_results = search_tour_heritage(
            query=place_query,
            place=place,
            pagination_token=pagination_token,
            page_size=page_size,
        )

        results = [r for r in search_results.get("results", []) if r.get("place") == place]
        next_token = search_results.get("next_token") if len(results) >= page_size else None
        return {"results": results, "next_token": next_token}

    except Exception as e:
        print(f"Error in get_heritage_guide: {str(e)}" )
        return {
            "results": [],
            "next_token": None,
            "error": str(e)
        }
    

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