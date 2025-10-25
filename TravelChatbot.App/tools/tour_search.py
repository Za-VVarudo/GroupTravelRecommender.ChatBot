import chromadb
from chromadb.utils import embedding_functions
from typing import List, Dict, Any, Optional
from models.tour import Tour
from config import OPENAI_ENDPOINT, OPENAI_TEXT_EMBEDED_API_KEY, OPENAI_TEXT_EMBEDED_DEPLOYMENT_NAME
import re

# Initialize ChromaDB client
chroma_client = chromadb.PersistentClient(path="./data/chroma")

# Use OpenAI embeddings
embedding_function = embedding_functions.OpenAIEmbeddingFunction(
    api_key= OPENAI_TEXT_EMBEDED_API_KEY,  # This should be loaded from environment variables
    model_name= OPENAI_TEXT_EMBEDED_DEPLOYMENT_NAME,
    api_base= OPENAI_ENDPOINT
)

# Create or get collection for tours
tour_collection = chroma_client.get_or_create_collection(
    name="tours",
    embedding_function=embedding_function
)

def embed_tours(tours: List[Dict[str, Any]]) -> None:
    """
    Embed tour information in ChromaDB for semantic search.
    
    Args:
        tours (List[Dict[str, Any]]): List of tour dictionaries to embed
    """
    # First, clear existing embeddings to avoid duplicates
    tour_collection.delete(ids=[tour["tourId"] for tour in tours])
    
    # Prepare data for embedding
    documents = []
    metadatas = []
    ids = []
    
    for tour in tours:
        # Create searchable text from tour data
        search_text = f"Tour in {tour['place']}: {tour['title']}. Price: {tour['price']} VND"
        documents.append(search_text)
        metadatas.append(tour)
        ids.append(tour["tourId"])
    
    # Add to collection
    tour_collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )

def search_tours(query: str) -> List[Dict[str, Any]]:
    """
    Search tours using natural language queries.
    
    Args:
        query (str): Natural language query (e.g., "tours in Hoi An", "tours under 600000 VND")
        
    Returns:
        List[Dict[str, Any]]: List of matching tour dictionaries
    """
    # Check for price-based queries
    price_match = re.search(r'under\s+(\d+(?:,\d{3})*)\s*(?:vnd|VND)?', query, re.IGNORECASE)
    
    if price_match:
        # Extract price value
        price_str = price_match.group(1).replace(',', '')
        max_price = int(price_str)
        
        # Query based on metadata
        results = tour_collection.query(
            query_texts=["tour"],  # Generic query to get all tours
            where={"price": {"$lt": max_price}},
            include=["metadatas"]
        )
    else:
        # Regular semantic search
        results = tour_collection.query(
            query_texts=[query],
            n_results=10,
            include=["metadatas"]
        )
    
    # Return the tour data from metadata
    return [item for item in results['metadatas'][0]]