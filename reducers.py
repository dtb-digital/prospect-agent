from typing import List, Dict
from langchain_core.messages import BaseMessage
from models import UserBase

def add_messages(old_messages: List[BaseMessage], new_messages: List[BaseMessage]) -> List[BaseMessage]:
    """Reducer for å kombinere meldinger"""
    return old_messages + new_messages

def add_users(old_users: List[Dict], new_users: List[Dict]) -> List[Dict]:
    """Reducer for å oppdatere eller legge til brukere"""
    email_to_user = {user['email']: UserBase(**user).model_dump() for user in old_users}
    for new_user in new_users:
        if new_user['email'] in email_to_user:
            email_to_user[new_user['email']].update(UserBase(**new_user).model_dump())
        else:
            email_to_user[new_user['email']] = UserBase(**new_user).model_dump()
    return list(email_to_user.values()) 