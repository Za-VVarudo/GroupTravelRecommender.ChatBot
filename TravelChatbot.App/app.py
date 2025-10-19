import os
from dotenv import load_dotenv
from openai import AzureOpenAI
from tools.tour_tools import get_registered_tours, get_registered_tours_function
from config import validate_config
from config import OPENAI_ENDPOINT, OPENAI_API_KEY, OPENAI_DEPLOYMENT_NAME

# --- Load environment ---
load_dotenv()
validate_config()

# --- Azure OpenAI client ---
client = AzureOpenAI(
    api_key=OPENAI_API_KEY,
    azure_endpoint=OPENAI_ENDPOINT,
    api_version="2024-10-01-preview",
)

def main():
    while True:
        print("\n=== Main Menu ===")
        print("1. General Chat")
        print("2. Get Registered Tours")
        print("3. Dummy Mode")
        print("0. Exit")
        choice = input("Select option: ").strip()

        if choice == "0":
            break

        elif choice == "1":
            prompt = input("You: ")
            resp = client.chat.completions.create(
                model=OPENAI_DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            print("Assistant:", resp.choices[0].message.content)

        elif choice == "2":
            phone = input("Enter phone number: ").strip()
            resp = client.chat.completions.create(
                model=OPENAI_DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": "You are a travel assistant that fetches user tours."},
                    {"role": "user", "content": f"My phone number is {phone}. Please find my registered tours."}
                ],
                tools=[get_registered_tours_function],
                tool_choice={"type": "function", "function": {"name": "get_registered_tours"}},
                temperature=0.3
            )

            message = resp.choices[0].message
            if getattr(message, "tool_calls", None):
                for call in message.tool_calls:
                    if call.function.name == "get_registered_tours":
                        args = call.function.arguments
                        if isinstance(args, str):
                            import json
                            args = json.loads(args)
                        result = get_registered_tours(args["phoneNumber"])
                        print("Assistant:", result)
            else:
                print("Assistant:", message.content)

        elif choice == "3":
            prompt = input("Say something: ")
            resp = client.chat.completions.create(
                model=OPENAI_DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": "You are a sarcastic but funny chatbot."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.9
            )
            print("Assistant:", resp.choices[0].message.content)

        else:
            print("Invalid choice. Try again.")

if __name__ == "__main__":
    main()
