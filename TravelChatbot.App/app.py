from config import validate_config
from config import OPENAI_ENDPOINT, OPENAI_API_KEY, OPENAI_DEPLOYMENT_NAME
from dotenv import load_dotenv
import json
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

message = None

def main():
    while True:
        print("\n=== Main Menu ===")
        print("1. Retrieve exising tours")
        print("2. Get registered tours")
        print("3. Register for a tour")
        print("0. Exit")
        choice = input("Select option: ").strip()

        if choice == "0":
            break

        elif choice == "1":
            prompt = input("Enter a desired place to search (optional): ")
            if not prompt:
                print("No place provided. Fetching all tours.")
                prompt
            else:
                prompt = f"I want to find tours in {prompt}."    

            resp = client.chat.completions.create(
                model=OPENAI_DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": "You are a travel assistant that fetches already existing tours."},
                    {"role": "user", "content": prompt }
                ],
                tools=[get_tours_function],
                tool_choice={"type": "function", "function": {"name": "get_tours"}}
            )
            message = resp.choices[0].message

        elif choice == "2":
            phone = input("Enter phone number: ").strip()
            resp = client.chat.completions.create(
                model=OPENAI_DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": "You are a travel assistant that fetches user tours."},
                    {"role": "user", "content": f"My phone number is {phone}. Please find my registered tours."}
                ],
                tools=[get_registered_tours_function],
                tool_choice={"type": "function", "function": {"name": "get_registered_tours"}}
            )
            message = resp.choices[0].message

        elif choice == "3":
            tour_id = input("Enter tourId: ").strip()
            phone = input("Enter phone number: ").strip()
            resp = client.chat.completions.create(
                model=OPENAI_DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": "You are a travel assistant that registers a user for a tour."},
                    {"role": "user", "content": f"I want to register tour {tour_id} for phone number {phone}."}
                ],
                tools=[register_tour_function],
                tool_choice={"type": "function", "function": {"name": "register_tour"}}
            )
            message = resp.choices[0].message

        else:
            print("Invalid choice. Try again.")
        
        if getattr(message, "tool_calls", None):
            for call in message.tool_calls:
                match call.function.name:
                    case "get_registered_tours":
                        args = call.function.arguments
                        if isinstance(args, str):
                            args = json.loads(args)
                        result = get_registered_tours(args["phoneNumber"])
                        print("Assistant:\n")
                        if not result:
                            print("No tours found.\n")
                        for tour in result:
                            print(tour)
                            print("\n")

                    case "get_tours":
                        args = call.function.arguments
                        if isinstance(args, str):
                            args = json.loads(args)
                        place = args.get("place")
                        result = get_tours(place)
                        print("Assistant:\n")
                        if not result:
                            print("No tours found.\n")

                        for tour in result:
                            print(tour)
                            print("\n")
                    
                    case "register_tour":
                        args = call.function.arguments
                        if isinstance(args, str):
                            args = json.loads(args)
                        try:
                            result = register_tour(args["tourId"], args["phoneNumber"])
                            # If the function returns an error dict, show it
                            if isinstance(result, dict) and result.get("error"):
                                print("Assistant:", result["error"])
                            else:
                                print("Assistant: Registration successful.")
                                print(result)
                        except ValueError as ve:
                            # Known validation errors like "tour not found" or "tour is registered"
                            print("Assistant:", str(ve))
                        except Exception as exc:
                            # Any other unexpected error
                            print("Assistant: An error occurred while registering the tour.")
                            print("Error:", str(exc))
        else:
            print("Assistant:", message.content)
            print("\n")

if __name__ == "__main__":
    main()
