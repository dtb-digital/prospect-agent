from typing import Dict, Optional, List
from langchain_core.tools import StructuredTool, BaseTool
from pydantic import BaseModel, Field
import requests
import os
from models import (
    LinkedInInput,
    HunterInput,
    HunterResponse,
    State
)
import json
from dotenv import load_dotenv
from langsmith import traceable

load_dotenv()

class LinkedInAPIError(Exception):
    """Custom error for LinkedIn API issues"""
    pass

class HunterAPIError(Exception):
    """Custom error for Hunter API issues"""
    pass

def get_linkedin_profile(linkedin_url: str) -> Dict:
    """Henter LinkedIn profil data via RapidAPI."""
    headers = {
        'X-RapidAPI-Key': os.getenv('RAPIDAPI_KEY'),
        'X-RapidAPI-Host': 'fresh-linkedin-profile-data.p.rapidapi.com'
    }
    
    try:
        response = requests.get(
            "https://fresh-linkedin-profile-data.p.rapidapi.com/get-linkedin-profile",
            params={
                "linkedin_url": linkedin_url,
                "include_skills": "false",
                "include_certifications": "false",
                "include_publications": "false",
                "include_honors": "false",
                "include_volunteers": "false",
                "include_projects": "false",
                "include_patents": "false",
                "include_courses": "false",
                "include_organizations": "false",
                "include_profile_status": "false",
                "include_company_public_url": "false"
            },
            headers=headers
        )
        response.raise_for_status()
        return {"data": response.json()["data"]}  # Wrap i data-felt
        
    except requests.RequestException as e:
        raise LinkedInAPIError(f"LinkedIn API error: {str(e)}")

# Definer LinkedIn tool
linkedin_tool = StructuredTool(
    name="linkedin",
    description="Henter LinkedIn data",
    func=get_linkedin_profile,
    args_schema=LinkedInInput
)

def get_hunter_data(domain: str, api_key: str, offset: int = 0, limit: int = 50) -> Dict:
    """Henter brukerdata fra Hunter.io API med paginering."""
    try:
        response = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={
                "domain": domain,
                "api_key": api_key,
                "offset": offset,
                "limit": limit
            }
        )
        response.raise_for_status()
        data = response.json()
        
        # Valider og strukturer responsen
        return HunterResponse(
            emails=data["data"]["emails"],
            meta={
                "total": data["meta"]["results"],
                "offset": offset,
                "limit": limit
            }
        ).dict()
        
    except requests.RequestException as e:
        raise HunterAPIError(f"Hunter API error: {str(e)}")

# Oppdater Hunter tool
hunter_tool = StructuredTool(
    name="hunter",
    description="Henter kontaktinfo",
    func=get_hunter_data,
    args_schema=HunterInput
)

# Attio CRM Tools
@traceable(name="create_person_in_attio")
def create_person_in_attio(person_data: str) -> str:
    """
    Oppretter en person i Attio CRM.
    
    Args:
        person_data: JSON-streng med persondata i Attio-format
        
    Returns:
        JSON-streng med respons fra Attio API
    """
    api_key = os.getenv("ATTIO_API_KEY")
    
    if not api_key:
        return "ATTIO_API_KEY må være satt i .env-filen"
    
    url = "https://api.attio.com/v2/objects/people/records"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    try:
        # Konverter streng til JSON hvis det er en streng
        if isinstance(person_data, str):
            data = json.loads(person_data)
        else:
            data = person_data
        
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code >= 400:
            return f"Feil ved oppretting av person i Attio: {response.text}"
        
        return json.dumps(response.json(), indent=2)
    
    except Exception as e:
        return f"Feil ved oppretting av person i Attio: {str(e)}"

@traceable(name="assert_person_in_attio", project=os.getenv("LANGCHAIN_PROJECT", "prospect-agent"))
def assert_person_in_attio(person_data: str) -> str:
    """
    Oppretter eller oppdaterer en person i Attio CRM.
    
    Args:
        person_data: JSON-streng med persondata i Attio-format
        
    Returns streng med respons fra Attio API
    """
    print(f"assert_person_in_attio kalt med: {person_data[:100]}...")
    api_key = os.getenv("ATTIO_API_KEY")
    
    if not api_key:
        return "ATTIO_API_KEY må være satt i .env-filen"
    
    # Bruk enkel POST for å opprette personer
    try:
        # Parse input data
        if isinstance(person_data, str):
            data = json.loads(person_data)
        else:
            data = person_data
            
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Bruk standard create-endepunkt
        create_url = "https://api.attio.com/v2/objects/people/records"
        print(f"Oppretter person med POST: {create_url}")
        print(f"Sender data til Attio: {json.dumps(data, indent=2)}")
        response = requests.post(create_url, headers=headers, json=data)
        
        print(f"Attio API respons status: {response.status_code}")
        print(f"Attio API respons: {response.text[:200]}...")
        
        if response.status_code >= 400:
            return f"Feil ved oppretting av person i Attio: {response.text}"
        
        return json.dumps(response.json(), indent=2)
        
    except Exception as e:
        print(f"Feil i assert_person_in_attio: {str(e)}")
        return f"Feil ved oppretting av person i Attio: {str(e)}"

@traceable(name="create_note_in_attio", project=os.getenv("LANGCHAIN_PROJECT", "prospect-agent"))
def create_note_in_attio(note_data: str) -> str:
    """
    Oppretter et notat i Attio CRM.
    
    Args:
        note_data: JSON-streng med notatdata i Attio-format
        
    Returns streng med respons fra Attio API
    """
    print(f"create_note_in_attio kalt med: {note_data[:100]}...")
    api_key = os.getenv("ATTIO_API_KEY")
    
    if not api_key:
        return "ATTIO_API_KEY må være satt i .env-filen"
    
    url = "https://api.attio.com/v2/notes"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    try:
        # Konverter streng til JSON hvis det er en streng
        if isinstance(note_data, str):
            data = json.loads(note_data)
        else:
            data = note_data
        
        print(f"Sender data til Attio: {json.dumps(data, indent=2)}")
        response = requests.post(url, headers=headers, json=data)
        
        print(f"Attio API respons status: {response.status_code}")
        print(f"Attio API respons: {response.text[:200]}...")
        
        if response.status_code >= 400:
            return f"Feil ved oppretting av notat i Attio: {response.text}"
        
        return json.dumps(response.json(), indent=2)
    
    except Exception as e:
        print(f"Feil i create_note_in_attio: {str(e)}")
        return f"Feil ved oppretting av notat i Attio: {str(e)}"

@traceable(name="get_attio_person_schema", project=os.getenv("LANGCHAIN_PROJECT", "prospect-agent"))
def get_attio_person_schema() -> str:
    """
    Henter skjema for personer i Attio.
    
    Returns streng med JSON-skjema for personer
    """
    return """
    {
      "data": {
        "values": {
          "email_addresses": ["email@example.com"],
          "name": "Fullt navn",
          "job_title": "Stillingstittel",
          "linkedin": "LinkedIn URL",
          "phone_numbers": ["Telefonnummer"]
        }
      }
    }
    """

@traceable(name="get_attio_note_schema", project=os.getenv("LANGCHAIN_PROJECT", "prospect-agent"))
def get_attio_note_schema() -> str:
    """
    Henter skjema for notater i Attio.
    
    Returns streng med JSON-skjema for notater
    """
    return """
    {
      "data": {
        "parent_object": "people",
        "parent_record_id": "record_id_streng_her",
        "title": "Notat-tittel",
        "format": "plaintext",
        "content": "Notat-innhold med \\n for linjeskift"
      }
    }
    """ 