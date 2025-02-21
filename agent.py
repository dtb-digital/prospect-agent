from typing import Annotated, List, Dict, Union, TypedDict, Any
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph
from langchain_core.runnables import RunnableConfig
from langsmith import traceable
from langsmith.wrappers import wrap_openai
from openai import OpenAI
import json
import os
from dotenv import load_dotenv
from tools import linkedin_tool, hunter_tool
from prompts import (
    ANALYSIS_PROMPT, 
    PRIORITY_PROMPT,
    validate_llm_output,
    get_model_schema,
)
from models import (
    SearchConfig, 
    PriorityAnalysis,
    HunterResponse,
    User
)
import logging
from langgraph.prebuilt import ToolNode, tools_condition
from langchain.prompts import ChatPromptTemplate
from system_prompts import ANALYSIS_SYSTEM_PROMPT, PRIORITY_SYSTEM_PROMPT

load_dotenv()

# Konfigurer logging
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')
for logger in ['langchain', 'langchain_core', 'langchain_openai', 'openai']:
    logging.getLogger(logger).setLevel(logging.ERROR)

# Configs
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0

# Wrap OpenAI client for better tracing
openai_client = wrap_openai(OpenAI())

# Definer state typer
MessageList = Annotated[List[BaseMessage], "messages"]
UserList = Annotated[List[Dict], "users"]

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], "messages"]
    users: Annotated[List[Dict], "users"]
    config: SearchConfig

# Opprett LLM instans
llm = ChatOpenAI(
    model_name=os.getenv("MODEL_NAME", DEFAULT_MODEL),
    temperature=float(os.getenv("TEMPERATURE", DEFAULT_TEMPERATURE))
)

# Legg til på toppen av filen, etter imports
def add_users(state: Dict, new_state: Dict) -> Dict:
    """Reducer for å oppdatere users i state"""
    state["users"] = new_state.get("users", state["users"])
    return state

def add_messages(state: Dict, new_state: Dict) -> Dict:
    """Reducer for å oppdatere messages i state"""
    state["messages"].extend(new_state.get("messages", []))
    return state

# Definer state updates
def update_state(state: Dict, new_state: Dict) -> Dict:
    """Oppdaterer state med nye verdier"""
    state.update(new_state)
    return state

# SCREENING NODE
@traceable(run_type="chain", name="hunter_collection")
def collect_hunter_data(state: AgentState, config: RunnableConfig) -> AgentState:
    """Henter kontakter fra Hunter.io"""
    try:
        hunter_data = hunter_tool.invoke({
            "domain": state["config"]["domain"],
            "api_key": os.getenv("HUNTER_API_KEY")
        })
        
        # Valider response med HunterResponse modell
        validated_data = HunterResponse(**hunter_data)
        
        users = [
            {
                "email": email["value"],
                "first_name": email.get("first_name"),
                "last_name": email.get("last_name"),
                "role": email.get("position"),
                "linkedin_url": email.get("linkedin"),
                "confidence": str(email.get("confidence", "")),
                "sources": ["hunter"]
            }
            for email in validated_data.emails
        ]
        
        return {
            "messages": state["messages"] + [
                ToolMessage(
                    tool_call_id="hunter_success",
                    tool_name="hunter",
                    content=f"Hentet {len(users)} kontakter"
                )
            ],
            "users": users,
            "config": state["config"]
        }
    except Exception as e:
        return {
            "messages": state["messages"] + [
                ToolMessage(
                    tool_call_id="hunter_error",
                    tool_name="hunter",
                    content=f"Feil: {str(e)}"
                )
            ],
            "users": [],
            "config": state["config"]
        }

# PRIORITERING NODE
@traceable(run_type="chain", name="prioritize_users")
def prioritize_users(state: AgentState, config: RunnableConfig) -> AgentState:
    """Prioriterer brukere basert på deres egnethet for målrollen."""
    users_with_roles = [u for u in state["users"] if u.get("role")]
    
    if not users_with_roles:
        return {
            "messages": state["messages"] + [HumanMessage(content="Ingen brukere med roller funnet")],
            "users": [],
            "config": state["config"]
        }
    
    try:
        # Formater meldinger direkte
        messages = [
            SystemMessage(content=PRIORITY_SYSTEM_PROMPT),
            HumanMessage(content=PRIORITY_PROMPT.format(
                target_role=state['config']['target_role'],
                prospects=json.dumps(users_with_roles, indent=2),
                available_data=json.dumps({"domain": state['config']['domain']}, indent=2),
                model_schema=get_model_schema(PriorityAnalysis),
                max_results=state['config'].get('max_results', 5)
            ))
        ]
        response = llm.invoke(messages)
        if isinstance(response, AIMessage):
            analysis = PriorityAnalysis(**json.loads(response.content))
        else:
            raise ValueError(f"Uventet respons type: {type(response)}")
        
        # Match og oppdater brukere
        prioritized = []
        for user in users_with_roles:
            if user["email"] in {p.email for p in analysis.users}:
                priority_user = next(p for p in analysis.users if p.email == user["email"])
                prioritized.append({
                    **user,
                    "priority_score": priority_user.score,
                    "priority_reason": priority_user.reason,
                    "sources": user["sources"] + ["prioritized"]
                })
        
        return {
            "messages": state["messages"] + [
                AIMessage(content=f"Prioriterte {len(prioritized)} brukere")
            ],
            "users": prioritized,
            "config": state["config"]
        }
    except Exception as e:
        logging.error(f"Feil i prioritering: {str(e)}")
        return {
            "messages": state["messages"] + [HumanMessage(content=f"Feil i prioritering: {str(e)}")],
            "users": state["users"],
            "config": state["config"]
        }

# LINKEDIN DATA NODE
@traceable(run_type="chain", name="get_linkedin_data")
def get_linkedin_data(state: AgentState, config: RunnableConfig) -> AgentState:
    """Henter LinkedIn data for prioriterte brukere."""
    prioritized_users = [u for u in state["users"] 
                        if "prioritized" in u.get("sources", [])
                        and u.get("linkedin_url")]
    
    if not prioritized_users:
        return {
            "messages": state["messages"] + [HumanMessage(content="Ingen brukere å berike")],
            "users": state["users"],
            "config": state["config"]
        }
    
    enriched = []
    messages = []
    
    for user in prioritized_users:
        try:
            linkedin_data = linkedin_tool.invoke({"linkedin_url": user["linkedin_url"]})
            enriched_user = {
                **user,
                "linkedin_raw": linkedin_data["data"],
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
        "messages": state["messages"] + messages,
        "users": enriched or state["users"],
        "config": state["config"]
    }

# ANALYSE NODE
@traceable(run_type="chain", name="analyze_profiles")
def analyze_profiles(state: AgentState, config: RunnableConfig) -> AgentState:
    """Analyserer LinkedIn profiler."""
    users_to_analyze = [u for u in state["users"] 
                       if "linkedin" in u.get("sources", [])]
    
    if not users_to_analyze:
        return {
            "messages": state["messages"] + [HumanMessage(content="Ingen profiler å analysere")],
            "users": state["users"],
            "config": state["config"]
        }
    
    analyzed = []
    messages = []
    
    for user in users_to_analyze:
        try:
            profile_data = {**user, **user["linkedin_raw"]}
            
            # Kjør én samlet analyse
            messages = [
                SystemMessage(content=ANALYSIS_SYSTEM_PROMPT),
                HumanMessage(content=ANALYSIS_PROMPT.format(
                    raw_profile=json.dumps(profile_data, indent=2),
                    target_role=state["config"]["target_role"],
                    model_schema=get_model_schema(User)
                ))
            ]
            response = llm.invoke(messages)
            if isinstance(response, AIMessage):
                analysis_results = validate_llm_output(response.content, User)
            else:
                raise ValueError(f"Uventet respons type: {type(response)}")
            
            analyzed_user = {
                **user,
                **analysis_results,  # Flater ut analysen direkte i bruker-objektet
                "sources": user["sources"] + ["analyzed"]
            }
            analyzed.append(analyzed_user)
            messages.extend([
                ToolMessage(
                    tool_call_id=f"analyze_{user['email']}",
                    tool_name="analyze",
                    content=f"Analyserte profil for {user['email']}"
                ),
                AIMessage(content=f"Analyse fullført for {user['email']}")
            ])
        except Exception as e:
            messages.extend([
                ToolMessage(
                    tool_call_id=f"analyze_error_{user['email']}",
                    tool_name="analyze",
                    content=f"Feil: {str(e)}"
                ),
                AIMessage(content=f"Analyse feilet for {user['email']}")
            ])
    
    return {
        "messages": state["messages"] + messages,
        "users": analyzed or state["users"],
        "config": state["config"]
    }

# Oppdater workflow
def create_workflow() -> StateGraph:
    """Oppretter workflow."""
    workflow = StateGraph(AgentState)
    
    # Legg til noder
    workflow.add_node("collect", collect_hunter_data)
    workflow.add_node("prioritize", prioritize_users)
    workflow.add_node("get_linkedin_data", get_linkedin_data)
    workflow.add_node("analyze", analyze_profiles)
    workflow.add_node("tools", ToolNode([linkedin_tool, hunter_tool]))
    
    # Sett entry point
    workflow.set_entry_point("collect")
    
    # Definer flyt
    workflow.add_edge("collect", "prioritize")
    workflow.add_edge("prioritize", "get_linkedin_data")
    workflow.add_edge("get_linkedin_data", "analyze")
    workflow.add_edge("analyze", "tools")
    workflow.add_edge("tools", "analyze")
    
    # Betinget routing
    workflow.add_conditional_edges(
        "collect",
        lambda s: "prioritize" if s["users"] else "__end__"
    )
    workflow.add_conditional_edges(
        "analyze",
        tools_condition,
        {
            "tools": "tools",
            "__end__": "__end__"
        }
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