import os
import json
import sys

# Legg til prosjektets rotmappe i sys.path for å kunne importere fra agent.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import create_attio_agent
from langchain_core.messages import AIMessage
from tools import get_attio_person_schema, get_attio_note_schema

# Last inn testdata
with open(os.path.join(os.path.dirname(__file__), "test_data.json"), "r") as f:
    test_data = json.load(f)

# Velg en person fra dataene (Karina Brix)
user_data = test_data["users"][1]  # Karina er den andre personen i listen

# Opprett Attio-agenten
agent = create_attio_agent()

# Debug: Skriv ut brukerdata
print("Brukerdata som sendes til agenten:")
print(json.dumps(user_data, indent=2))

# Debug: Hent skjemaer
print("\nAttio Person Schema:")
print(get_attio_person_schema())
print("\nAttio Note Schema:")
print(get_attio_note_schema())

# Kjør agenten med brukerdataene
print("Kjører agenten med brukerdata...")
print(f"Bruker {len(user_data)} felt i brukerdataene")

# Konverter brukerdata til en streng for agenten
result = agent.invoke({"user_data": json.dumps(user_data, ensure_ascii=False)})

# Skriv ut hele resultatet for debugging
print("\nFullstendig resultat fra agenten:")
print(json.dumps(result, indent=2, default=str))

print("CRM-integrasjon resultat:")
# Håndter AIMessage-objekter
if isinstance(result, AIMessage):
    print(f"Respons fra agenten: {result.content}")
else:
    # Prøv å konvertere til en serialiserbar form
    serializable_result = {
        "content": result.content if hasattr(result, "content") else str(result)
    }
    print(json.dumps(serializable_result, indent=2)) 