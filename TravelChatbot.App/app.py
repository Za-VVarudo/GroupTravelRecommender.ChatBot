from datetime import datetime
from config import validate_config
from config import OPENAI_ENDPOINT, OPENAI_API_KEY, OPENAI_DEPLOYMENT_NAME
from dotenv import load_dotenv
import json
import streamlit as st
from openai import AzureOpenAI
from tools.tour_tools import (
    get_tours,
    get_tours_function,
    get_heritage_guide,
    get_heritage_guide_function,
    register_tour,
    register_tour_function,
    get_registered_tours,
    get_registered_tours_function
)

# --- Load environment ---
load_dotenv()
validate_config()

# --- Azure OpenAI client ---
client = AzureOpenAI(
    api_key=OPENAI_API_KEY,
    azure_endpoint=OPENAI_ENDPOINT,
    api_version="2024-10-01-preview",
)

# --- Page config ---
st.set_page_config(page_title="Travel Chatbot", page_icon="✈️")
st.title("Travel Chatbot 🌍")

def main():
    # Initialize chat history and pagination state
    if "messages" not in st.session_state:
        st.session_state.messages = []
        st.session_state.tour_next_token = None
        st.session_state.heritage_next_token = None
        st.session_state.last_place = None
        st.session_state.messages.append({
            "role": "assistant",
            "content": "Hello! I'm your travel assistant. I can help you with:\n"
                      "- Searching for available tours\n"
                      "- Finding heritage guide information about places\n"
                      "- Checking your registered tours\n"
                      "- Registering for a tour\n\n"
                      "You can ask me about tours or cultural heritage information for any place. What would you like to know?"
        })

    # TODO: Voice to text input
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    # Chat input
    if prompt := st.chat_input("What can I help you with?"):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        # Show assistant response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                # Determine which function to use based on user input
                resp = client.chat.completions.create(
                    model=OPENAI_DEPLOYMENT_NAME,
                    messages=[
                        {"role": "system", "content": """You are a travel assistant that can help users with:
1. Searching for tours and their details
2. Searching heritage guide information about specific places or cultural sites
3. Checking their registered tours
4. Registering for tours

For heritage guide searches:
- Use the get_heritage_guide function when searching for cultural or historical information
- Always include both 'place' and 'search_query' parameters when possible
- If the user only gives a place (e.g. 'Get me tour heritage in Hue'), infer a relevant search_query automatically, such as 'heritage sites', 'tourist information', or 'places to visit'

For tour searches:
- Use the get_tours function to find available tours
- Results will show tour details including dates and prices

Based on the user's request, use the appropriate function and parameters."""},
                        *[{"role": msg["role"], "content": msg["content"]} for msg in st.session_state.messages]
                    ],
                    tools=[get_tours_function, get_heritage_guide_function, get_registered_tours_function, register_tour_function]
                )

                message = resp.choices[0].message
                response_content = ""
                
                if message.tool_calls:
                    for call in message.tool_calls:
                        match call.function.name:
                            case "get_registered_tours":
                                args = json.loads(call.function.arguments)
                                registered_tours = get_registered_tours(args["phoneNumber"])
                                if not registered_tours:
                                    response_content = "I couldn't find any registered tours for that phone number."
                                else:
                                    response_content = "Here are your registered tours:\n\n"
                                    for reg_tour in registered_tours:
                                        # Get full tour details from ChromaDB using tourId
                                        tour_details = get_tours(search_query=f"tourId {reg_tour['tourId']}")
                                        if tour_details:
                                            tour = tour_details[0]
                                            start = datetime.fromtimestamp(tour["startDate"]).strftime("%Y-%m-%d")
                                            end = datetime.fromtimestamp(tour["endDate"]).strftime("%Y-%m-%d")
                                            reg_date = datetime.fromtimestamp(reg_tour["createAt"]).strftime("%Y-%m-%d %H:%M")
                                            response_content += f"""🎫 **Booking Details**
- **Registration Date:** {reg_date}
- **Tour:** {tour['title']}
- **Place:** {tour['place']}
- **Duration:** {start} → {end}
- **Price:** {tour['price']:,} VND
- **Category:** {tour['category']}
- **Status:** {tour['status']}
- **Herigate guide:** {tour['heritageGuide']}
- **Tour ID:** {tour['tourId']}\n\n"""
                                        else:
                                            response_content += f"⚠️ Tour with ID {reg_tour['tourId']} not found in the system.\n\n"

                            case "get_tours":
                                args = json.loads(call.function.arguments)
                                place = args.get("place")
                                search_query = args.get("search_query")
                                pagination_token = args.get("pagination_token")
                                page_size = args.get("page_size", 3)
                                
                                result = get_tours(
                                    place=place, 
                                    search_query=search_query,
                                    pagination_token=pagination_token,
                                    page_size=page_size
                                )
                                
                                if not result or not result.get("results"):
                                    response_content = "I couldn't find any tours matching your criteria."
                                else:
                                    tours = result["results"]
                                    next_token = result.get("next_token")
                                    # Store the next token and current place in session state
                                    st.session_state.tour_next_token = next_token
                                    st.session_state.last_place = place
                                    response_content = "Here are the available tours:\n\n"
                                    for tour in tours:
                                        start = datetime.fromtimestamp(tour["startDate"]).strftime("%Y-%m-%d")
                                        end = datetime.fromtimestamp(tour["endDate"]).strftime("%Y-%m-%d")
                                        response_content += f"""🏞️ **{tour['title']}**
- **Place:** {tour['place']}
- **Category:** {tour['category']}
- **Duration:** {start} → {end}
- **Price:** {tour['price']:,} VND
- **Status:** {tour['status']}
- **Heritage Guide:** {tour['heritageGuide']}
- **Tour ID:** {tour.get('tourId', 'N/A')}

"""
                            case "get_heritage_guide":
                                args = json.loads(call.function.arguments)
                                place = args["place"]
                                search_query = args.get("search_query")
                                pagination_token = args.get("pagination_token")
                                page_size = args.get("page_size", 3)
                                print(f"Calling get_heritage_guide with place: {place}, search_query: {search_query}, pagination_token: {pagination_token}, page_size: {page_size}, args: {args}")
                                result = get_heritage_guide(
                                    place=place,
                                    search_query=search_query,
                                    pagination_token=pagination_token,
                                    page_size=page_size
                                )
                                
                                if not result or not result.get("results"):
                                    response_content = f"I couldn't find any heritage guides for {place}."
                                else:
                                    guides = result["results"]
                                    next_token = result.get("next_token")
                                    # Store the next token and current place in session state
                                    st.session_state.heritage_next_token = next_token
                                    st.session_state.last_place = place
                                    
                                    # Create context from the heritage guides
                                    context = "\n".join([guide.get("raw_text", "") for guide in guides])
                                    # Get a natural response from OpenAI using the context
                                    llm_response = client.chat.completions.create(
                                        model=OPENAI_DEPLOYMENT_NAME,
                                        messages=[
                                            {"role": "system", "content": f"""
You are a knowledgeable travel assistant. Use only the information from the Heritage Guide Context to answer the user query. 
Do not use external knowledge. If the answer is not in the context, respond: "I don't know based on the provided guide."

Heritage Guide Context:
----------------------
{context}
"""},
                                            {"role": "user", "content": prompt}
                                        ]
                                    )
                                    
                                    response_content = llm_response.choices[0].message.content
                                    
                                    if next_token:
                                        response_content += "\n\n_There are more heritage guides available. You can ask for more information to see the next page._"
                            
                            case "register_tour":
                                args = json.loads(call.function.arguments)
                                try:
                                    result = register_tour(args["tourId"], args["phoneNumber"])
                                    if isinstance(result, dict) and result.get("error"):
                                        response_content = f"❌ {result['error']}"
                                    else:
                                        response_content = "✅ Registration successful! Here are your booking details:\n\n"
                                        response_content += str(result)
                                        response_content += "\nDo you want to get registered tours now?"
                                except ValueError as ve:
                                    response_content = f"❌ {str(ve)}"
                                except Exception as exc:
                                    response_content = f"❌ An error occurred while registering the tour: {str(exc)}"
                else:
                    response_content = message.content

                st.write(response_content)
                st.session_state.messages.append({"role": "assistant", "content": response_content})

if __name__ == "__main__":
    main()
