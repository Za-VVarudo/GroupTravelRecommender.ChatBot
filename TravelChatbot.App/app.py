from datetime import datetime
from config import validate_config
from config import OPENAI_ENDPOINT, OPENAI_API_KEY, OPENAI_DEPLOYMENT_NAME
from dotenv import load_dotenv
import json
import streamlit as st
from openai import AzureOpenAI
from tools.tour_tools import get_registered_tours, get_registered_tours_function, get_tours, get_tours_function, register_tour, register_tour_function

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
    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []
        st.session_state.messages.append({
            "role": "assistant",
            "content": "Hello! I'm your travel assistant. I can help you with:\n"
                      "- Searching for available tours\n"
                      "- Checking your registered tours\n"
                      "- Registering for a tour\n\n"
                      "What would you like to do?"
        })

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
                        {"role": "system", "content": "You are a travel assistant that can help users search for tours, check their registered tours, and register for tours. Based on the user's request, use the appropriate function."},
                        *[{"role": msg["role"], "content": msg["content"]} for msg in st.session_state.messages]
                    ],
                    tools=[get_tours_function, get_registered_tours_function, register_tour_function]
                )

                message = resp.choices[0].message
                response_content = ""
                
                if message.tool_calls:
                    for call in message.tool_calls:
                        match call.function.name:
                            case "get_registered_tours":
                                args = json.loads(call.function.arguments)
                                result = get_registered_tours(args["phoneNumber"])
                                if not result:
                                    response_content = "I couldn't find any registered tours for that phone number."
                                else:
                                    response_content = "Here are your registered tours:\n\n"
                                    for tour in result:
                                        response_content += str(tour) + "\n\n"

                            case "get_tours":
                                args = json.loads(call.function.arguments)
                                place = args.get("place")
                                result = get_tours(place)
                                if not result:
                                    response_content = "I couldn't find any tours matching your criteria."
                                else:
                                    response_content = "Here are the available tours:\n\n"
                                    for tour in result:
                                        start = datetime.fromtimestamp(tour["startDate"]).strftime("%Y-%m-%d")
                                        end = datetime.fromtimestamp(tour["endDate"]).strftime("%Y-%m-%d")
                                        response_content += f"""🏞️ **{tour['title']}**
- **Place:** {tour['place']}
- **Category:** {tour['category']}
- **Duration:** {start} → {end}
- **Price:** {tour['price']:,} VND
- **Status:** {tour['status']}
- **Tour ID:** {tour.get('id', 'N/A')}

"""
                            
                            case "register_tour":
                                args = json.loads(call.function.arguments)
                                try:
                                    result = register_tour(args["tourId"], args["phoneNumber"])
                                    if isinstance(result, dict) and result.get("error"):
                                        response_content = f"❌ {result['error']}"
                                    else:
                                        response_content = "✅ Registration successful! Here are your booking details:\n\n"
                                        response_content += str(result)
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
