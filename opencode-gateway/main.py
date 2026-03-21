# Opencode IDE Agent Gateway
# TODO: Implement FastAPI app for IDE agent gateway

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.vault import router as vault_router

app = FastAPI()

# Allow local UI to call endpoints; restrict in production via env config
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

# Mount Vault / runbook handlers
app.include_router(vault_router)

# TODO: Add mTLS authentication, Prometheus metrics, LMDeploy integration
