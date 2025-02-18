from typing import TypedDict, Annotated, List
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph
from dotenv import load_dotenv
import os
import requests
from langsmith import traceable

load_dotenv()

# Define User type
class User(TypedDict):
    email: str
    first_name: str
    last_name: str
    role: str
    confidence: str
    linkedin_url: str
    phone_number: str

# Define message reducer
def add_messages(old_messages: List[BaseMessage], new_messages: List[BaseMessage]) -> List[BaseMessage]:
    return old_messages + new_messages

# Define user reducer
def add_users(old_users: List[User], new_users: List[User]) -> List[User]:
    email_to_user = {user['email']: user for user in old_users}
    for new_user in new_users:
        email_to_user[new_user['email']] = new_user
    return list(email_to_user.values())

# Define state
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    domain: str
    role: str
    users: Annotated[List[User], add_users]
    prioritizedUsers: Annotated[List[User], add_users]
    finalUsers: Annotated[List[User], add_users]

# Define hunter search node
@traceable(run_type="chain", name="hunter_search")
def hunter_search(state: AgentState, config: dict = None):
    hunter_api_key = os.getenv("HUNTER_API_KEY")
    response = requests.get(
        "https://api.hunter.io/v2/domain-search",
        params={
            "domain": state["domain"],
            "api_key": hunter_api_key,
            "limit": 25
        }
    )
    
    if not response.ok:
        return {
            "messages": [HumanMessage(content=f"Hunter API error: {response.status_code}")],
            "users": []
        }
    
    data = response.json()
    users = [
        {
            "email": email["value"],
            "first_name": email.get("first_name", ""),
            "last_name": email.get("last_name", ""),
            "role": email.get("position", ""),
            "confidence": str(email.get("confidence", "")),
            "linkedin_url": email.get("linkedin", ""),
            "phone_number": email.get("phone_number", "")
        }
        for email in data["data"]["emails"]
    ]
    
    return {
        "messages": [HumanMessage(content="Hunter.io search completed")],
        "users": users
    }

# Setup workflow
workflow = StateGraph(AgentState)
workflow.add_node("hunter_search", hunter_search)
workflow.set_entry_point("hunter_search")
workflow.set_finish_point("hunter_search")

# Compile workflow
app = workflow.compile()

# Test
if __name__ == "__main__":
    result = app.invoke({
        "messages": [],
        "domain": "documaster.com",
        "role": "",
        "users": [],
        "prioritizedUsers": [],
        "finalUsers": []
    })
    
    print("\nFinal State:")
    print(f"Messages: {[m.content for m in result['messages']]}")
    print(f"\nFound {len(result['users'])} users:")
    for user in result['users']:
        print(f"- {user['first_name']} {user['last_name']}")
        print(f"  Role: {user['role']}")
        print(f"  Email: {user['email']}")
        print(f"  Confidence: {user['confidence']}")
        if user['linkedin_url']:
            print(f"  LinkedIn: {user['linkedin_url']}")
        print()