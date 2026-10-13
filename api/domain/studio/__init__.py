"""
Task Studio (beta): upload a project plus a prompt; a Pro model does the work and returns the updated
project as a zip, a plain README and a PDF report.

  sources.py    Strategy  - zip / loose files / folder upload -> Project
  providers.py  Strategy + Adapter + Registry - who does the work (Gemini today)
  pipeline.py   Template Method - load -> context -> provider -> validate -> outputs
  builders.py   Builder   - output zip and the PDF report
  routes.py     HTTP layer (blueprint studio_bp, /api/studio)
"""
from api.domain.studio.routes import studio_bp  # noqa: F401
