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
@traceable(name="create_person_in_attio", project=os.getenv("LANGCHAIN_PROJECT", "prospect-agent"))
def create_person_in_attio(user: dict) -> dict:
    """
    Oppretter en person i Attio basert på brukerdata.
    
    Args:
        user: Brukerdata med email, first_name, last_name, etc.
        
    Returns:
        Respons fra Attio API
    """
    print(f"create_person_in_attio kalt med bruker: {user.get('email')}")
    
    # Sjekk om vi har nødvendig informasjon
    if not user.get("email") or not user.get("first_name"):
        return {"error": "Mangler nødvendig informasjon (email eller first_name)"}
    
    # Opprett person i Attio
    try:
        # Opprett data for Attio API
        data = {
            "data": {
                "values": {
                    "email_addresses": [user.get("email")],
                    "name": f"{user.get('first_name')} {user.get('last_name', '')}".strip(),
                    "job_title": user.get("role") or user.get("career", {}).get("current_role", ""),
                    "linkedin": user.get("linkedin_url", "")
                }
            }
        }
        
        # Opprett personen i Attio
        api_key = os.getenv("ATTIO_API_KEY")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        url = "https://api.attio.com/v2/objects/people/records"
        print(f"Oppretter person med POST: {url}")
        print(f"Sender data til Attio: {json.dumps(data, indent=2)}")
        
        response = requests.post(url, headers=headers, json=data)
        print(f"Attio API respons status: {response.status_code}")
        print(f"Attio API respons: {response.text[:200]}...")
        
        # Sjekk om responsen er vellykket
        response.raise_for_status()
        
        # Returner responsen som JSON
        print(f"create_person_in_attio response: {json.dumps(response.json(), indent=2)}")
        return response.json()
    except Exception as e:
        print(f"Feil ved oppretting av person i Attio: {e}")
        # Returner en feilmelding i stedet for å kaste en exception
        return {"error": str(e)}

@traceable(name="create_note_in_attio", project=os.getenv("LANGCHAIN_PROJECT", "prospect-agent"))
def create_note_in_attio(note_params: dict) -> dict:
    """
    Oppretter et notat i Attio CRM knyttet til en person.
    
    Args:
        note_params: Dictionary med notatdata
            - person_id: ID til personen notatet skal knyttes til
            - content: Innholdet i notatet
            - title: (valgfritt) Tittel på notatet
            
    Returns:
        Dictionary med API-respons eller feilmelding
    """
    print(f"create_note_in_attio kalt med person_id: {note_params.get('person_id')}")
    
    try:
        # Ekstraher nødvendige felter
        person_id = note_params.get("person_id")
        content = note_params.get("content", "")
        
        # Generer en tittel hvis den ikke er gitt
        title = note_params.get("title")
        if not title and content:
            # Bruk første linje som tittel, eller de første 50 tegnene
            first_line = content.split('\n', 1)[0].strip()
            if first_line.startswith('# '):
                title = first_line[2:]  # Fjern markdown-overskrift
            else:
                title = first_line[:50] + ('...' if len(first_line) > 50 else '')
        
        # Sjekk at vi har nødvendige data
        if not person_id or not content:
            return {"error": "Mangler nødvendig informasjon (person_id eller content)"}
        
        if not title:
            title = "Notat fra Prospect Agent"
        
        # Hvis person_id er et objekt, hent ut record_id
        if isinstance(person_id, dict) and "record_id" in person_id:
            person_id = person_id["record_id"]
            
        # Fjern "person_" prefikset hvis det finnes
        if isinstance(person_id, str) and person_id.startswith("person_"):
            person_id = person_id[7:]  # Fjern "person_" prefikset
        
        # Opprett data for Attio API
        data = {
            "data": {
                "parent_object": "people",
                "parent_record_id": person_id,
                "title": title,
                "format": "plaintext",
                "content": content
            }
        }
        
        # Opprett notatet i Attio
        api_key = os.getenv("ATTIO_API_KEY")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        url = "https://api.attio.com/v2/notes"
        print(f"Oppretter notat med POST: {url}")
        print(f"Sender data til Attio: {json.dumps(data, indent=2)}")
        
        response = requests.post(url, headers=headers, json=data)
        print(f"Attio API respons status: {response.status_code}")
        print(f"Attio API respons: {response.text[:200]}...")
        
        # Sjekk om responsen er vellykket
        response.raise_for_status()
        
        # Returner responsen som JSON
        print(f"create_note_in_attio response: {json.dumps(response.json(), indent=2)}")
        return response.json()
    except Exception as e:
        print(f"Feil ved oppretting av notat i Attio: {e}")
        # Returner en feilmelding i stedet for å kaste en exception
        return {"error": str(e)}

def test_hunter_api(domain: str = "documaster.com") -> Dict:
    """
    Tester Hunter API direkte for å sjekke om det fungerer.
    
    Args:
        domain: Domenet som skal søkes etter
        
    Returns:
        Dictionary med API-respons eller feilmelding
    """
    print(f"Tester Hunter API for domenet {domain}")
    
    try:
        # Hent API-nøkkel fra miljøvariabel
        api_key = os.getenv("HUNTER_API_KEY")
        if not api_key:
            return {"error": "HUNTER_API_KEY er ikke satt i miljøvariablene"}
        
        print(f"Hunter API-nøkkel er satt")
        
        # Kall Hunter API direkte
        response = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={
                "domain": domain,
                "api_key": api_key,
                "offset": 0,
                "limit": 50
            }
        )
        
        print(f"Hunter API respons status: {response.status_code}")
        
        # Sjekk om responsen er vellykket
        response.raise_for_status()
        
        # Returner responsen som JSON
        data = response.json()
        print(f"Hunter API returnerte {len(data.get('data', {}).get('emails', []))} e-poster")
        
        return data
    except Exception as e:
        print(f"Feil ved testing av Hunter API: {e}")
        return {"error": str(e)}
