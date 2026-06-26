#!/usr/bin/env python3
"""
RAG query wrapper - produces same quality answers as Telegram bot
Usage: python3 rag_query.py "your question"
"""

import sys
from src.dementia_rag import answer_from_dementia_knowledge

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 rag_query.py 'your question'")
        print("Example: python3 rag_query.py What is dementia")
        sys.exit(1)
    
    question = " ".join(sys.argv[1:])
    
    print(f"\nQuestion: {question}")
    print("=" * 70)
    
    try:
        answer = answer_from_dementia_knowledge(question)
        print("\n" + answer)
    except Exception as e:
        print(f"\nError: {e}")
        print("\nSuggestions:")
        print("1. Check if database exists: ls -la .chroma/ling_rag/")
        print("2. Try reindexing: python3 -m src.cli --force-reindex")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    main()