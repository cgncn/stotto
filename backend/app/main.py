from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import pools, admin, auth, users, subscriptions
from app.api.webhooks import stripe as stripe_webhook

app = FastAPI(
    title="STOTTO API",
    description="Spor Toto haftalık 15 maç karar destek sistemi",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health_check():
    return {"status": "ok"}


app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(pools.router, prefix="/weekly-pools", tags=["pools"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(subscriptions.router, prefix="/subscriptions", tags=["subscriptions"])
app.include_router(stripe_webhook.router, prefix="/webhooks", tags=["webhooks"])
