import os
import json
import sys

# Legg til prosjektets rotmappe i sys.path for å kunne importere fra agent.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import create_attio_agent
from langchain_core.messages import AIMessage
from tools import get_attio_person_schema, get_attio_note_schema

# Last inn testdata
with open("tests/test_data.json", "r") as f:
    user_data = json.load(f)

# Skriv ut brukerdata
print(f"Brukerdata som sendes til agenten:")
print(json.dumps(user_data, indent=2, ensure_ascii=False))

# Skriv ut antall felt
print(f"Bruker {len(user_data.keys())} felt i brukerdataene\n")

# Hent Attio-skjemaer for debugging
print("\nAttio Person Schema:\n")
print(get_attio_person_schema())
print("\nAttio Note Schema:\n")
print(get_attio_note_schema())
print("\nKjører agenten med brukerdata...")

# Opprett agent
agent = create_attio_agent()

# Kjør agenten
result = agent({"input": json.dumps(user_data, ensure_ascii=False)})

print(f"Resultat: {result}")

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