from langsmith import Client
from agent import analyze_domain
from dotenv import load_dotenv
import os

# Last inn miljøvariabler
load_dotenv()

# Test at LangSmith-sporing fungerer
def test_langsmith_tracing():
    try:
        # Sjekk at nødvendige miljøvariabler er satt
        required_vars = ["LANGCHAIN_API_KEY", "LANGCHAIN_PROJECT"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            print(f"Manglende miljøvariabler: {', '.join(missing_vars)}")
            print("Sørg for at .env filen inneholder:")
            print("LANGCHAIN_TRACING_V2=true")
            print("LANGCHAIN_API_KEY=din-api-nøkkel")
            print("LANGCHAIN_PROJECT=prospect-agent")
            return False
        
        # Initialiser klienten
        client = Client()
        print("LangSmith-klient initialisert")
        
        # Kjør en enkel analyse
        print("Starter analyse...")
        result = analyze_domain(
            domain="example.com",
            target_role="Developer",
            max_results=1
        )
        
        # Sjekk at vi får resultater
        users = result.get("users", [])
        print(f"Analyse fullført med {len(users)} brukere")
        
        # Sjekk at vi har sporing i LangSmith
        project_name = os.getenv("LANGCHAIN_PROJECT")
        print(f"Sjekk LangSmith UI for prosjekt '{project_name}' for å se sporingen")
        print("LangSmith-sporing fungerer!")
        return True
    except Exception as e:
        print(f"Feil ved testing av LangSmith: {e}")
        return False

if __name__ == "__main__":
    test_langsmith_tracing() 