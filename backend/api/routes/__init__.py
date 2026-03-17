"""Route modules registered by the FastAPI app."""

from . import admin, auth, health, query, sessions, trademark, verdict

__all__ = [
	"admin",
	"auth",
	"health",
	"query",
	"sessions",
	"trademark",
	"verdict",
]
