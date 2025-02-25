from typing import Annotated, List, Dict, Union, TypedDict, Any, Optional, Type
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import START, END, StateGraph
from langchain_core.runnables import RunnableConfig
from langsmith import traceable
from langsmith.wrappers import wrap_openai
from openai import OpenAI
import json
import os
from dotenv import load_dotenv
from pydantic import BaseModel
from tools import linkedin_tool, hunter_tool
from models import (
    SearchConfig, 
    PriorityAnalysis,
    HunterResponse,
    User,
    State,
)
from langchain_core.prompts import ChatPromptTemplate
from system_prompts import ANALYSIS_SYSTEM_PROMPT, PRIORITY_SYSTEM_PROMPT

load_dotenv()

def get_model_schema(model_class: Type[BaseModel]) -> str:
    """Henter JSON schema for en modell i lesbart format"""
    schema = model_class.model_json_schema()
    return json.dumps(schema, indent=2, ensure_ascii=False)

# Configs
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0

# Wrap OpenAI client for better tracing
openai_client = wrap_openai(OpenAI())

# Initialiser LLM
llm = ChatOpenAI(
    model_name=os.getenv("MODEL_NAME", DEFAULT_MODEL),
    temperature=float(os.getenv("TEMPERATURE", DEFAULT_TEMPERATURE))
)

# Definer prompts
ANALYSIS_PROMPT = """
Analyser denne LinkedIn-profilen grundig:

PROFIL:
{raw_profile}

MÅLROLLE:
{target_role}

TILGJENGELIG DATA:
{available_data}

FORVENTET OUTPUT FORMAT:
{schema}
"""

PRIORITY_PROMPT = """Evaluer og prioriter disse brukerne for {target_role}.
Max resultater: {max_results}

BRUKERE:
{users}

TILGJENGELIG DATA:
{available_data}

FORVENTET OUTPUT FORMAT:
{schema}
"""

# Bind modeller til strukturert output
analysis_chain = (
    ChatPromptTemplate.from_messages([
        ("system", ANALYSIS_SYSTEM_PROMPT),
        ("human", ANALYSIS_PROMPT)
    ])
    | llm.with_structured_output(User, method="json_mode")
)

priority_chain = (
    ChatPromptTemplate.from_messages([
        ("system", PRIORITY_SYSTEM_PROMPT),
        ("human", PRIORITY_PROMPT)
    ])
    | llm.with_structured_output(PriorityAnalysis, method="json_mode")
)

# SCREENING NODE
@traceable(run_type="chain", name="hunter_collection")
def collect_hunter_data(state: dict, config: RunnableConfig) -> dict:
    """Henter kontakter fra Hunter.io"""
    try:
        hunter_data = hunter_tool.invoke({
            "domain": state["config"]["domain"],
            "api_key": os.getenv("HUNTER_API_KEY")
        })
        
        validated_data = HunterResponse(**hunter_data)
        
        return {
            "messages": [
                ToolMessage(
                    tool_call_id="hunter_success",
                    tool_name="hunter",
                    content=f"Hentet {len(validated_data.emails)} kontakter"
                )
            ],
            "users": [{"email": email["value"], "first_name": email.get("first_name"), "last_name": email.get("last_name"), "role": email.get("position"), "linkedin_url": email.get("linkedin"), "confidence": str(email.get("confidence")) if email.get("confidence") else None, "sources": ["hunter"]} for email in validated_data.emails],
            "config": state["config"]
        }
    except Exception as e:
        return {
            "messages": [
                ToolMessage(
                    tool_call_id="hunter_error",
                    tool_name="hunter",
                    content=f"Feil: {str(e)}"
                )
            ],
            "users": [],
        }

# PRIORITERING NODE
@traceable(run_type="chain", name="prioritize_users")
def prioritize_users(state: dict, config: RunnableConfig) -> dict:
    """Prioriterer brukere basert på deres egnethet for målrollen."""
    # Hent alle brukere fra state
    all_users = state["users"]
    
    if not all_users:
        return {
            "messages": [HumanMessage(content="Ingen brukere å prioritere")],
            "users": [],
            "config": state["config"]
        }
    
    try:
        response = priority_chain.invoke({
            "target_role": state['config']['target_role'],
            "users": json.dumps(all_users, indent=2),
            "available_data": json.dumps({"domain": state['config']['domain']}, indent=2),
            "max_results": state['config'].get('max_results', 5),
            "schema": get_model_schema(PriorityAnalysis)
        })
        
        try:
            # Start med alle brukere
            updated_users = all_users.copy()
            
            # Oppdater de som ble prioritert
            for i, user in enumerate(updated_users):
                if user["email"] in {p.email for p in response.users}:
                    priority_user = next(p for p in response.users if p.email == user["email"])
                    # Valider score
                    if not 0 <= priority_user.score <= 1:
                        raise ValueError(f"Ugyldig score {priority_user.score} for {user['email']}")
                    updated_users[i] = {
                        **user,
                        "priority_score": priority_user.score,
                        "priority_reason": priority_user.reason,
                        "sources": user["sources"] + ["prioritized"]
                    }
            
            return {
                "messages": [
                    AIMessage(content=f"Prioriterte {len(response.users)} brukere")
                ],
                "users": updated_users,
                "config": state["config"]
            }
        except json.JSONDecodeError as je:
            raise ValueError("Kunne ikke parse prioriteringsrespons som JSON")
        except Exception as ve:
            raise ValueError("Validering av prioriteringsrespons feilet")
            
    except Exception as e:
        return {
            "messages": [HumanMessage(content=f"Feil i prioritering: {str(e)}")],
            "users": state["users"],
            "config": state["config"]
        }

# LINKEDIN DATA NODE
@traceable(run_type="chain", name="get_linkedin_data")
def get_linkedin_data(state: dict, config: RunnableConfig) -> dict:
    """Henter LinkedIn data for prioriterte brukere."""
    prioritized_users = [u for u in state["users"] 
                        if "prioritized" in u.get("sources", [])
                        and u.get("linkedin_url")]
    
    if not prioritized_users:
        return {
            "messages": [HumanMessage(content="Ingen brukere å berike")],
            "users": state["users"],
        }
    
    enriched = []
    messages = []
    
    for user in prioritized_users:
        try:
            linkedin_data = linkedin_tool.invoke({"linkedin_url": user["linkedin_url"]})
            enriched_user = {
                **user,
                "linkedin_raw_data": linkedin_data["data"],
                "sources": user["sources"] + ["linkedin"]
            }
            enriched.append(enriched_user)
            messages.append(
                ToolMessage(
                    tool_call_id=f"linkedin_{user['email']}",
                    tool_name="linkedin",
                    content=f"Hentet LinkedIn data for {user['email']}"
                )
            )
        except Exception as e:
            messages.append(
                ToolMessage(
                    tool_call_id=f"linkedin_error_{user['email']}",
                    tool_name="linkedin",
                    content=f"Feil: {str(e)}"
                )
            )
    
    return {
        "messages": messages,
        "users": enriched,
    }

# ANALYSE NODE
@traceable(run_type="chain", name="analyze_profiles")
def analyze_profiles(state: dict, config: RunnableConfig) -> dict:
    """Analyserer LinkedIn profiler."""
    users_to_analyze = [u for u in state["users"] 
                       if "linkedin" in u.get("sources", [])
                       and "linkedin_raw_data" in u]
    
    if not users_to_analyze:
        return {
            "messages": [SystemMessage(content="Ingen profiler å analysere")],
            "users": state["users"],
        }
    
    analyzed = []
    messages = []
    
    for user in users_to_analyze:
        try:
            response = analysis_chain.invoke({
                "raw_profile": json.dumps(user["linkedin_raw_data"], indent=2),
                "target_role": state["config"]["target_role"],
                "available_data": json.dumps({"domain": state['config']['domain']}, indent=2),
                "schema": get_model_schema(User)
            })
            
            try:
                analysis_results = response.dict()
                
                # Behold bare spesifikke felter fra original bruker
                analyzed_user = {
                    **analysis_results,  # Nye data først
                    "sources": user["sources"] + ["analyzed"]
                }
                # Fjern rådata etter analyse
                analyzed_user.pop("linkedin_raw_data", None)
                analyzed.append(analyzed_user)
                
                messages.append(
                    ToolMessage(
                        tool_call_id=f"analyze_{user['email']}",
                        tool_name="analyze",
                        content=f"Analyserte profil for {user['email']}"
                    )
                )
            except json.JSONDecodeError as je:
                raise ValueError(f"Kunne ikke parse JSON fra LLM respons for {user['email']}")
            except Exception as ve:
                raise ValueError(f"Validering feilet for {user['email']}")
                
        except Exception as e:
            messages.append(
                ToolMessage(
                    tool_call_id=f"analyze_error_{user['email']}",
                    tool_name="analyze",
                    content=f"Feil ved analyse av {user['email']}: {str(e)}"
                )
            )
    
    return {
        "messages": messages,
        "users": analyzed,
    }

# Oppdater workflow
def create_workflow() -> StateGraph:
    """Oppretter workflow."""
    workflow = StateGraph(State)
    
    # Legg til noder
    workflow.add_node("collect", collect_hunter_data)
    workflow.add_node("prioritize", prioritize_users)
    workflow.add_node("get_linkedin_data", get_linkedin_data)
    workflow.add_node("analyze", analyze_profiles)
    
    # Definer flyt med START og END
    workflow.add_edge(START, "collect")
    workflow.add_edge("collect", "prioritize")
    workflow.add_edge("prioritize", "get_linkedin_data")
    workflow.add_edge("get_linkedin_data", "analyze")
    workflow.add_edge("analyze", END)
    
    # Betinget routing - stopp hvis ingen brukere funnet
    workflow.add_conditional_edges(
        "collect",
        lambda s: "prioritize" if s["users"] else END
    )

    return workflow.compile()

def get_config() -> RunnableConfig:
    return RunnableConfig(
        callbacks=[],
        tags=["prospect-agent"],
        metadata={"version": "1.0"}
    )

# Compile workflow
app = create_workflow()

def analyze_domain(
    domain: str,
    target_role: str,
    max_results: int = 5
) -> Dict[str, Any]:
    """Kjør full analyse av et domene."""
    return app.invoke({
        "messages": [],
        "users": [],
        "config": SearchConfig(
            domain=domain,
            target_role=target_role,
            max_results=max_results
        )
    })

__all__ = ['app', 'get_config', 'analyze_domain']