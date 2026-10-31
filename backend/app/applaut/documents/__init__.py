"""Applaut AI's document engine (docs/applaut/APPLAUT_AI_ENGINE_DESIGN.md §6-7).

Layout is code (fixed templates); content comes from the user's master profile.
Code picks the bullets, orders the skills and writes the fixed parts of the
cover letter; a model writes only the CV headline and three cover-letter
paragraphs, which the fact guard checks before anything is rendered.
"""
