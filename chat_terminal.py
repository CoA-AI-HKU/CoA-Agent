# Terminal: python chat_terminal.py

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.experimental.memory_routine_agent import (
    handle_personal_memory,
    handle_routine_request,
    handle_activity_request,
    load_user_profile
)

# ============================================
# 🎯 FOOLPROOF USER SELECTION
# The script asks you which profile to load EVERY TIME you run it.
# No more editing the file!
# ============================================
print("=" * 60)
print("👤 Which user do you want to test?")
print("   1. 眉眉婆婆 (test_meimei) - Dementia patient")
print("   2. 陳亞明 (test_ah_ming) - Healthy male")
print("=" * 60)

choice = input("Enter 1 or 2: ").strip()

if choice == "1":
    USER_ID = "test_meimei"
elif choice == "2":
    USER_ID = "test_ah_ming"
else:
    print("Invalid choice. Defaulting to 眉眉婆婆.")
    USER_ID = "test_meimei"

# ============================================
# DEBUG: Print the loaded profile
# ============================================
profile = load_user_profile(USER_ID)
print("=" * 60)
print(f"🧪 Terminal Chat Mode")
print(f"   User ID: {USER_ID}")
print(f"   Loaded Profile Name: {profile.get('name', '⚠️ NOT FOUND!')}")
print(f"   Family: {profile.get('family', {})}")
print("=" * 60)
print("   Type 'exit' or 'quit' to stop.")
print("=" * 60)

while True:
    try:
        question = input("\nYou: ")
        if question.lower() in ["exit", "quit"]:
            print("Goodbye!")
            break
        
        if not question.strip():
            continue
            
        # --- Routing Logic ---
        if "停藥" in question or "食多" in question:
            result = handle_routine_request(question, USER_ID)
        elif "腦退化症" in question or "頭暈" in question or "唔舒服" in question:
            result = handle_routine_request(question, USER_ID)
        elif any(k in question for k in ["好悶", "聽粵曲", "聽歌", "睇舊相", "記憶練習", "有咩做"]):
            result = handle_activity_request(question, USER_ID)
        elif any(k in question for k in ["藥", "煮飯", "食咗", "食左"]):
            result = handle_routine_request(question, USER_ID)
        else:
            result = handle_personal_memory(question, USER_ID)
        
        answer = result.get("answer", "[No reply]")
        print(f"Bot: {answer}")
        
    except KeyboardInterrupt:
        print("\nGoodbye!")
        break
    except Exception as e:
        print(f"Error: {e}")
