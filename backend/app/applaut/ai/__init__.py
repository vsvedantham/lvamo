"""Applaut AI: the in-house model's work (docs/applaut/APPLAUT_AI_ENGINE_DESIGN.md).

provider.py  the model behind an interface (llama.cpp's OpenAI-compatible server)
prompts.py   what the model is asked, with JSON schemas for its answers
scoring.py   the model extracts facts; code turns them into the match score
queue.py     the FIFO queue of model work
handlers.py  one queue item: score a job, or write a job's documents
worker.py    the single process that serves the queue
nightly.py   22:00: discovery, raw jobs per user, queueing the scoring
"""
