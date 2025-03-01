"""
System prompts for prospect-agent.

Dette modulet henter prompter fra LangSmith Prompt Hub.
Hvis promptene ikke kan hentes, kastes en feil.
"""

from prompt_hub import get_prompt_from_hub

# Definer standardprompter som fallback
ANALYSIS_SYSTEM_PROMPT_DEFAULT = """
Du er en ekspert på å analysere LinkedIn-profiler for B2B-salg.
Din oppgave er å analysere profilen til en potensiell kunde og gi innsikt som kan hjelpe med salg.
Fokuser på personens rolle, erfaring, og hvordan ditt produkt kan løse deres problemer.
"""

PRIORITY_SYSTEM_PROMPT_DEFAULT = """
Du er en ekspert på å prioritere potensielle kunder for B2B-salg.
Din oppgave er å rangere en liste med potensielle kunder basert på hvor sannsynlig det er at de vil kjøpe produktet.
Fokuser på personens rolle, erfaring, og hvordan ditt produkt kan løse deres problemer.
"""

# Hent prompter fra LangSmith
def get_analysis_prompt():
    """Henter analyseprompt fra LangSmith."""
    prompt_name = "prospect-agent-analysis-prompt"
    print(f"Henter analyseprompt '{prompt_name}'...")
    return get_prompt_from_hub(prompt_name, ANALYSIS_SYSTEM_PROMPT_DEFAULT)

def get_priority_prompt():
    """Henter prioriteringsprompt fra LangSmith."""
    prompt_name = "prospect-agent-priority-prompt"
    print(f"Henter prioriteringsprompt '{prompt_name}'...")
    return get_prompt_from_hub(prompt_name, PRIORITY_SYSTEM_PROMPT_DEFAULT)

# Initialiser systemprompter
ANALYSIS_SYSTEM_PROMPT = get_analysis_prompt()
PRIORITY_SYSTEM_PROMPT = get_priority_prompt() 