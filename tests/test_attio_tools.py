import os
import json
import sys

# Legg til prosjektets rotmappe i sys.path for å kunne importere fra agent.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import assert_person_in_attio, create_note_in_attio

# Test assert_person_in_attio direkte
person_data = {
  "data": {
    "values": {
      "email_addresses": ["karina@firi.com"],
      "name": "Karina Brix",
      "job_title": "Country Manager",
      "linkedin": "https://www.linkedin.com/in/karinarothoffbrix",
      "phone_numbers": []
    }
  }
}

print("Testing assert_person_in_attio...")
person_result = assert_person_in_attio(json.dumps(person_data))
print(f"Resultat: {person_result}")

# Hvis person ble opprettet, lag et notat
try:
    person_response = json.loads(person_result)
    print(f"Person respons: {json.dumps(person_response, indent=2)}")
    if "data" in person_response and "id" in person_response["data"]:
        person_id = person_response["data"]["id"]
        print(f"Person ID: {person_id}")
        
        note_data = {
          "data": {
            "parent_object": "people",
            "parent_record_id": person_id["record_id"],
            "title": "Karina Brix - Country Manager at Firi",
            "format": "plaintext",
            "content": "Sammendrag:\nKarina er Country Manager for Firi i Danmark.\n\nKontaktinfo:\nEmail: karina@firi.com\nLinkedIn: https://www.linkedin.com/in/karinarothoffbrix"
          }
        }
        
        print("\nTesting create_note_in_attio...")
        note_result = create_note_in_attio(json.dumps(note_data))
        print(f"Resultat: {note_result}")
    else:
        print("Kunne ikke hente person_id fra responsen")
except Exception as e:
    print(f"Feil ved parsing av person-respons: {str(e)}") 