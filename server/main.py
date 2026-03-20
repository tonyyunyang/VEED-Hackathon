import os
import random
import json
import time
import math
from fastapi import FastAPI, HTTPException, Request
import contextvars
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, AsyncGenerator
import threading
from functools import lru_cache
from google import genai
from google.genai import types
import asyncio
from anyio import create_memory_object_stream
import uuid
import json_repair


app = FastAPI(title="VEED SERVER")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    expose_headers=["X-Process-Time"],
    max_age=3600,  # Cache preflight requests for 1 hour
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
