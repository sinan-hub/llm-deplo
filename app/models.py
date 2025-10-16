# app/models.py
from pydantic import BaseModel, Field
from typing import List, Optional

class Attachment(BaseModel):
    """Attachment with name and data URI"""
    name: str = Field(..., description="Filename of the attachment")
    url: str = Field(..., description="Data URI (e.g., data:image/png;base64,...)")

class TaskRequest(BaseModel):
    """Request schema for building/updating an app"""
    email: str = Field(..., example="student@example.com", description="Student email ID")
    secret: str = Field(..., example="my-secret-token", description="Student-provided secret")
    task: str = Field(..., example="captcha-solver-abc123", description="Unique task ID")
    round: int = Field(..., example=1, ge=1, le=3, description="Round number (1 or 2)")
    nonce: str = Field(..., example="ab12-cd34-ef56", description="Unique nonce to pass back")
    brief: str = Field(
        ..., 
        example="Create a captcha solver that handles ?url=https://.../image.png",
        description="Description of what the app needs to do"
    )
    checks: List[str] = Field(
        default_factory=list,
        example=["Repo has MIT license", "README.md is professional"],
        description="Evaluation criteria"
    )
    evaluation_url: str = Field(
        ..., 
        example="https://example.com/notify",
        description="URL to send repo details after deployment"
    )
    attachments: List[Attachment] = Field(
        default_factory=list,
        description="Files encoded as data URIs"
    )

class TaskResponse(BaseModel):
    """Response after accepting a task"""
    status: str = Field(..., example="accepted")
    note: str = Field(..., example="processing round 1 started")

class ErrorResponse(BaseModel):
    """Error response"""
    error: str = Field(..., example="Invalid secret")

class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(default="healthy")
    service: str = Field(default="auto-app-builder")
    endpoints: List[str] = Field(default=["/api-endpoint"])