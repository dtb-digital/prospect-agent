from typing import Dict, Optional, List
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
import requests
import os

class LinkedInProfileResponse(BaseModel):
    """Strukturert respons fra LinkedIn API"""
    about: Optional[str] = Field(None, description="Profilbeskrivelse")
    experiences: List[dict] = Field(default_factory=list, description="Arbeidserfaring")
    educations: List[dict] = Field(default_factory=list, description="Utdanning")
    languages: List[dict] = Field(default_factory=list, description="Språk")
    follower_count: Optional[int] = None
    connection_count: Optional[int] = None
    location: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None
    current_company_start: Optional[str] = None  # Nytt felt for å beregne tid i nåværende bedrift

# Input schema for LinkedIn tool
class LinkedInInput(BaseModel):
    linkedin_url: str = Field(..., description="LinkedIn profil URL")

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
        data = response.json()["data"]
        
        # Valider og strukturer responsen
        return LinkedInProfileResponse(**data).dict()
        
    except requests.RequestException as e:
        raise Exception(f"LinkedIn API error: {str(e)}")

# Definer LinkedIn tool
linkedin_tool = StructuredTool(
    name="get_linkedin_profile",
    description="Henter og validerer LinkedIn profil data",
    func=get_linkedin_profile,
    args_schema=LinkedInInput,
    return_type=LinkedInProfileResponse
)

# Input schema for Hunter tool
class HunterInput(BaseModel):
    domain: str = Field(..., description="Domenet å søke i")
    api_key: str = Field(..., description="Hunter.io API nøkkel")

def get_hunter_data(domain: str, api_key: str) -> Dict:
    """Henter brukerdata fra Hunter.io API."""
    try:
        response = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={
                "domain": domain,
                "api_key": api_key,
                "limit": 50
            }
        )
        response.raise_for_status()
        return response.json()
        
    except requests.RequestException as e:
        raise Exception(f"Hunter API error: {str(e)}")

# Definer Hunter tool
hunter_tool = StructuredTool(
    name="get_hunter_data",
    description="Henter brukerdata fra Hunter.io",
    func=get_hunter_data,
    args_schema=HunterInput,
    return_type=dict
) 