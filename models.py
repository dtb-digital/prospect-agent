from typing import List, Dict, Optional, Any
from typing_extensions import TypedDict
from pydantic import BaseModel, Field, model_serializer
from langchain_core.messages import BaseMessage
import json
# Fjern eller kommenter ut unødvendige loggmeldinger
# logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

class UserBase(BaseModel):
    """Base modell for grunnleggende brukerdata"""
    # Base info
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[str] = None
    confidence: Optional[str] = None
    
    # Hunter.io data
    linkedin_url: Optional[str] = None
    phone_number: Optional[str] = None
    
    # Metadata
    sources: List[str] = Field(default_factory=list)
    priority_score: Optional[float] = None
    priority_reason: Optional[str] = None
    screening_score: Optional[float] = None
    screening_reason: Optional[str] = None

class LinkedInRawData(BaseModel):
    """Rå data fra LinkedIn API"""
    """
    Generisk container for LinkedIn data.
    LLM vil mappe rå API-data til denne strukturen.
    """
    data: Dict[str, Any] = Field(description="Rå data fra LinkedIn API")

class LinkedInAnalysis(BaseModel):
    """Analyse av LinkedIn profil"""
    # Basis info
    first_name: Optional[str] = Field(None, description="Fornavn")
    last_name: Optional[str] = Field(None, description="Etternavn")
    full_name: Optional[str] = Field(None, description="Fullt navn")
    headline: Optional[str] = Field(None, description="Tittel/overskrift")
    
    # Nåværende rolle
    job_title: Optional[str] = Field(None, description="Nåværende stillingstittel")
    company: Optional[str] = Field(None, description="Nåværende selskap")
    company_industry: Optional[str] = Field(None, description="Selskapets bransje")
    years_in_role: Optional[int] = Field(None, description="Antall år i nåværende rolle")
    years_in_company: Optional[int] = Field(None, description="Antall år i nåværende selskap")
    
    # Erfaring
    total_experience_years: Optional[int] = Field(None, description="Totalt antall års erfaring")
    key_skills: List[str] = Field(default_factory=list, description="Viktigste ferdigheter")
    industries: List[str] = Field(default_factory=list, description="Bransjeerfaring")
    
    # Utdanning
    education_level: Optional[str] = Field(None, description="Høyeste utdanningsnivå")
    education_field: Optional[str] = Field(None, description="Utdanningsfelt")
    
    # Nettverk
    connection_count: Optional[int] = Field(None, description="Antall forbindelser")
    follower_count: Optional[int] = Field(None, description="Antall følgere")
    
    # Analyse
    seniority_level: Optional[str] = Field(None, description="Vurdering av erfaringsnivå")
    role_relevance: Optional[float] = Field(None, description="Relevans for målrollen (0-1)")
    overall_summary: Optional[str] = Field(None, description="Overordnet vurdering")

class EnrichedUser(UserBase):
    """Bruker med all beriket data"""
    linkedin_raw: Optional[LinkedInRawData] = None
    linkedin_analysis: Optional[LinkedInAnalysis] = None

    def model_dump(self, **kwargs):
        """Overstyr model_dump for å håndtere nested objekter"""
        data = super().model_dump(**kwargs)
        if self.linkedin_raw:
            data['linkedin_raw'] = self.linkedin_raw.model_dump()
        if self.linkedin_analysis:
            data['linkedin_analysis'] = self.linkedin_analysis.model_dump()
        return data
    
    def ser_model(self) -> Dict:
        """Flat serialisering av modellen"""
        return self.model_dump()

class SearchConfig(TypedDict):
    domain: str
    target_role: str
    search_depth: int
    max_results: int

class AgentState(TypedDict):
    messages: List[BaseMessage]
    config: SearchConfig
    users: List[Dict[str, Any]]

class LinkedInInput(BaseModel):
    """Input for LinkedIn API"""
    linkedin_url: str = Field(..., description="LinkedIn profil URL")

class HunterInput(BaseModel):
    """Input for Hunter API"""
    domain: str = Field(..., description="Domenet å søke i")
    api_key: str = Field(..., description="Hunter.io API nøkkel")
    offset: int = Field(default=0, description="Offset for paginering")
    limit: int = Field(default=50, description="Antall resultater per side")

class HunterResponse(BaseModel):
    """Strukturert respons fra Hunter API"""
    emails: List[dict] = Field(..., description="Liste over e-poster")
    meta: dict = Field(..., description="Metadata inkludert antall sider")

class PriorityAnalysis(BaseModel):
    """Analyse av brukers egnethet for målrollen"""
    users: Dict[str, dict] = Field(description="Dictionary med email som nøkkel og analyse som verdi") 