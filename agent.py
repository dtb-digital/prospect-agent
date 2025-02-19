from typing import Annotated, List, Optional, Dict
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END, START
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field
from langsmith import traceable
from langsmith.wrappers import wrap_openai
from openai import OpenAI
import json
import os
from dotenv import load_dotenv
from tools import linkedin_tool, hunter_tool, LinkedInProfileResponse
from prompts import LINKEDIN_ANALYSIS_PROMPT, PRIORITY_ANALYSIS_PROMPT

load_dotenv()

# Configs
DEFAULT_MODEL = "gpt-4o-mini"  # eller "gpt-3.5-turbo" basert på behov
DEFAULT_TEMPERATURE = 0

# Wrap OpenAI client for better tracing
openai_client = wrap_openai(OpenAI())

# User model with enrichment fields -> # Brukermodell med berikelsesfelter
class User(TypedDict, total=False):  # Legg til total=False for å gjøre alle felter valgfrie
    # Base info -> # Grunnleggende info
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    role: Optional[str]
    confidence: Optional[str]
    
    # Hunter.io data -> # Hunter.io data
    linkedin_url: Optional[str]
    phone_number: Optional[str]
    
    # LinkedIn enrichment -> # LinkedIn-berikelse
    summary: Optional[str]
    experience_years: Optional[int]
    current_company_years: Optional[float]
    key_skills: Optional[List[str]]
    leadership_experience: Optional[bool]
    education_level: Optional[str]
    profile_type: Optional[str]
    personality_traits: Optional[List[dict]]
    career_pattern: Optional[dict]
    education_pattern: Optional[dict]
    network_strength: Optional[dict]
    fun_facts: Optional[List[str]]
    
    # Metadata -> # Metadata
    sources: List[str]
    priority_score: Optional[float]
    priority_reason: Optional[str]
    screening_score: Optional[float]
    screening_reason: Optional[str]

# Search config -> # Søkekonfigurasjon
class SearchConfig(TypedDict):
    domain: str
    target_role: str
    search_depth: int
    max_results: Optional[int] = 5  # Ny parameter med default verdi

# Først definerer vi reducers
def add_messages(old_messages: List[BaseMessage], new_messages: List[BaseMessage]) -> List[BaseMessage]:
    return old_messages + new_messages

def add_users(old_users: List[User], new_users: List[User]) -> List[User]:
    """Reducer som oppdaterer eller legger til brukere basert på email."""
    email_to_user = {user['email']: user for user in old_users}
    for new_user in new_users:
        if new_user['email'] in email_to_user:
            email_to_user[new_user['email']].update(new_user)
        else:
            email_to_user[new_user['email']] = new_user
    return list(email_to_user.values())

# Så definerer vi state
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    config: SearchConfig
    users: Annotated[List[User], add_users]

# 3. SCREENING NODE (FØRSTE STEG)
class HunterDataCollector:
    """Samler kontakter fra Hunter.io API"""
    
    @traceable(
        run_type="chain",
        name="hunter_collection",
        metadata={"type": "data_collection"}
    )
    def run(self, state: AgentState, config: RunnableConfig) -> AgentState:
        """Henter alle kontakter fra Hunter.io"""
        messages = []
        users = []
        offset = 0
        limit = 50
        
        while True:
            try:
                # Hent batch med kontakter
                hunter_data = hunter_tool.invoke({
                    "domain": state["config"]["domain"],
                    "api_key": os.getenv("HUNTER_API_KEY"),
                    "offset": offset,
                    "limit": limit
                })
                
                if not hunter_data["emails"]:
                    break
                
                # Konverter direkte til User objekter
                for email in hunter_data["emails"]:
                    users.append({
                        "email": email["value"],
                        "first_name": email.get("first_name", ""),
                        "last_name": email.get("last_name", ""),
                        "role": email.get("position", ""),
                        "confidence": str(email.get("confidence", "")),
                        "linkedin_url": email.get("linkedin", ""),
                        "phone_number": email.get("phone_number", ""),
                        "sources": ["hunter"],
                        "department": email.get("department", ""),
                        "seniority": email.get("seniority", "")
                    })
                
                messages.append(
                    ToolMessage(
                        tool_call_id=f"hunter_batch_{offset}",
                        tool_name="hunter_collection",
                        content=f"Hentet {len(hunter_data['emails'])} kontakter"
                    )
                )
                
                # Gå til neste side
                offset += limit
                if offset >= hunter_data["meta"]["total"]:
                    break
                    
            except Exception as e:
                messages.append(
                    ToolMessage(
                        tool_call_id="hunter_error",
                        tool_name="hunter_collection",
                        content=f"Feil under henting av kontakter: {str(e)}"
                    )
                )
                break
        
        return {
            "messages": messages,
            "users": users
        }

# 4. PRIORITERING NODE (ANDRE STEG)
class PriorityAnalysis(BaseModel):
    """Analyse av brukers egnethet for målrollen"""
    users: Dict[str, dict] = Field(description="Dictionary med email som nøkkel og analyse som verdi")

@traceable(
    run_type="chain",
    name="prioritize_users",
    metadata={"type": "prioritization"}
)
def prioritize_users(state: AgentState, config: RunnableConfig) -> AgentState:
    """Prioriterer brukere basert på deres egnethet for målrollen."""
    
    # Setup LLM med strukturert output
    model = ChatOpenAI(
        model=DEFAULT_MODEL,
        temperature=DEFAULT_TEMPERATURE,
        api_key=os.getenv("OPENAI_API_KEY")  # Bruk API-nøkkel direkte
    ).with_structured_output(
        PriorityAnalysis,
        method="json_mode"
    )
    
    # Filtrer brukere med rolle
    users_to_analyze = [u for u in state["users"] if u.get("role")]
    
    if not users_to_analyze:
        return {
            "messages": [HumanMessage(content="Ingen brukere med roller funnet")],
            "users": []
        }
    
    # Analyser alle brukere i én forespørsel
    analysis = model.invoke(
        PRIORITY_ANALYSIS_PROMPT.format(
            role=state['config']['target_role'],
            max_results=state['config'].get('max_results', 5),
            users=json.dumps([{
                "name": f"{u['first_name']} {u['last_name']}",
                "role": u['role'],
                "email": u['email'],
                "linkedin_url": u.get('linkedin_url', ''),  # Legg til LinkedIn URL
                "confidence": u.get('confidence', ''),      # Legg til confidence score
                "department": u.get('department', ''),      # Legg til avdeling
                "seniority": u.get('seniority', '')        # Legg til ansiennitet
            } for u in users_to_analyze], indent=2)
        ),
        config=config
    )
    
    # Oppdater brukere med prioriteringer
    prioritized = []
    for user in users_to_analyze:
        analysis_result = analysis.users.get(user["email"])
        if analysis_result:  # Ta med alle som ble valgt av LLM
            prioritized.append({
                **user,
                "priority_score": analysis_result["score"],
                "priority_reason": analysis_result["reason"],
                "sources": user.get("sources", []) + ["prioritized"]
            })
    
    return {
        "messages": [HumanMessage(content=f"Analyserte {len(users_to_analyze)} brukere, prioriterte {len(prioritized)}")],
        "users": prioritized
    }

# 5. LINKEDIN NODE (SISTE STEG)
class LinkedInAnalysis(BaseModel):
    """Strukturert analyse av LinkedIn profil"""
    summary: str = Field(description="Kort profesjonell oppsummering")
    experience_years: int = Field(description="Totalt antall års relevant erfaring")
    current_company_years: float = Field(description="Antall år i nåværende bedrift")
    key_skills: List[str] = Field(description="Liste over relevante ferdigheter for målrollen")
    leadership_experience: bool = Field(description="Har personen ledererfaring")
    education_level: str = Field(
        description="Høyeste utdanningsnivå: 'Videregående', 'Bachelor', 'Master', 'PhD', eller 'Ukjent'"
    )
    profile_type: str = Field(description="Klassifisering av karrieretype")
    personality_traits: List[dict] = Field(description="Personlighetstrekk utledet fra profilen")
    career_pattern: dict = Field(description="Analyse av karrieremønster")
    education_pattern: dict = Field(description="Mønster i utdanning")
    network_strength: dict = Field(description="Nettverksstyrke: followers og connections")
    fun_facts: List[str] = Field(description="Interessante fakta om personen")

@traceable(
    run_type="chain",
    name="get_linkedin_info",
    metadata={"tool": "linkedin"}
)
def get_linkedin_info(state: AgentState, config: RunnableConfig) -> AgentState:
    """Beriker prioriterte brukere med LinkedIn data og analyse."""
    
    # Finn prioriterte brukere med LinkedIn URL og score
    prioritized_users = [
        u for u in state["users"] 
        if "prioritized" in u.get("sources", [])  # Sjekk at de er prioritert
        and u.get("linkedin_url")                 # Sjekk at de har LinkedIn URL
        and u.get("priority_score", 0) > 0        # Sjekk at de har fått en score
    ]
    
    if not prioritized_users:
        return {
            "messages": [HumanMessage(content="Ingen brukere nådde LinkedIn-terskelen")],
            "users": state["users"]  # Behold alle brukere, men uten LinkedIn-berikelse
        }
    
    # Setup LLM med strukturert output
    model = ChatOpenAI(
        model=DEFAULT_MODEL,
        temperature=DEFAULT_TEMPERATURE,
        api_key=os.getenv("OPENAI_API_KEY")  # Bruk API-nøkkel direkte
    ).with_structured_output(
        LinkedInAnalysis,
        method="json_mode"
    )
    
    # Hold styr på hvilke brukere som er oppdatert
    updated_users = {user["email"]: user for user in state["users"]}
    
    analysis_messages = []
    
    enriched = []
    
    for user in prioritized_users:
        try:
            # 1. Hent LinkedIn data via tool
            tool_message = ToolMessage(
                tool_call_id=f"linkedin_fetch_{user['email']}",
                tool_name="get_linkedin_profile",
                content=f"Henter LinkedIn-data for {user['email']}"
            )
            linkedin_data = linkedin_tool.invoke(user["linkedin_url"], config=config)
            
            # 2. Analyser profilen med LLM
            analysis = model.invoke(
                LINKEDIN_ANALYSIS_PROMPT.format(
                    role=state['config']['target_role'],
                    linkedin_data=json.dumps(linkedin_data, indent=2)
                ),
                config=config
            )
            
            # Oppdater bruker med LinkedIn data
            enriched_user = updated_users[user["email"]].copy()
            enriched_user.update({
                **{k: getattr(analysis, k) for k in [
                    "summary", "experience_years", "key_skills", "leadership_experience", 
                    "education_level", "profile_type", "personality_traits", "career_pattern",
                    "education_pattern", "network_strength", "fun_facts"
                ]},
                "sources": user.get("sources", []) + ["linkedin_analyzed"]
            })
            updated_users[user["email"]] = enriched_user
            
            analysis_messages.extend([
                tool_message,
                ToolMessage(
                    tool_call_id=f"linkedin_analysis_{user['email']}",
                    tool_name="analyze_linkedin",
                    content=f"Analyserte LinkedIn-profil for {user['email']}"
                )
            ])
            
            enriched.append(enriched_user)
            
        except Exception as e:
            analysis_messages.append(
                ToolMessage(
                    tool_call_id=f"linkedin_error_{user['email']}",
                    tool_name="get_linkedin_info",
                    content=f"Feil ved prosessering av LinkedIn-data for {user['email']}: {str(e)}"
                )
            )
    
    return {
        "messages": analysis_messages,
        "users": enriched  # Reduceren vil merge dette med eksisterende brukere
    }

# Workflow setup og kompilering -> # Arbeidsflyt oppsett og kompilering
def create_workflow() -> StateGraph:
    """Oppretter og konfigurerer workflow."""
    
    graph_builder = StateGraph(AgentState)
    
    # Initialiser collector
    hunter_collector = HunterDataCollector()
    
    # Legg til noder
    graph_builder.add_node("hunter_collection", hunter_collector.run)
    graph_builder.add_node("prioritize_users", prioritize_users)
    graph_builder.add_node("get_linkedin_info", get_linkedin_info)
    
    # Definer flyten
    graph_builder.add_edge(START, "hunter_collection")
    graph_builder.add_edge("hunter_collection", "prioritize_users")
    graph_builder.add_edge("prioritize_users", "get_linkedin_info")
    
    return graph_builder

def get_config() -> RunnableConfig:
    """Enkel konfigurasjon for testing."""
    return RunnableConfig(
        tags=["test", "prospect-agent"],  # Legg til flere relevante tags
        metadata={"version": "1.0"}  # Legg til metadata
    )

# Compile workflow
app = create_workflow().compile()

# Test
if __name__ == "__main__":
    result = app.invoke({
        "messages": [],
        "config": {
            "domain": "documaster.com",
            "target_role": "ansvarlig for digital eller markedsføring",
            "search_depth": 1,
            "max_results": 3  
        },
        "users": []
    })
    
    # Print berikede brukere
    print("\nBrukere med LinkedIn-analyse:")
    for user in result["users"]:
        if "linkedin_analyzed" in user.get("sources", []):
            print(f"\n{user['first_name']} {user['last_name']} ({user['email']}):")
            print(f"- Screening: {user.get('screening_score', 0)} - {user.get('screening_reason', 'Ingen begrunnelse')}")
            print(f"- Poengsum: {user['priority_score']}")
            print(f"- Oppsummering: {user.get('summary', 'Ingen oppsummering')}")
            print(f"- Ferdigheter: {', '.join(user.get('key_skills', []))}")
            print(f"- Erfaring: {user.get('experience_years', 0)} år")