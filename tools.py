from typing import Dict, Optional, List
from langchain_core.tools import StructuredTool, BaseTool
from pydantic import BaseModel, Field
import requests
import os
from models import (
    LinkedInRawData, 
    LinkedInInput,
    HunterInput,
    HunterResponse
)

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