from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routers import company

app = FastAPI(
    title="DART Risk Insight API",
    description="DART 공시 데이터를 기반으로 재무비율을 계산하고 LLM으로 리스크를 분석하는 API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(company.router)


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request: Request, exc: RuntimeError):
    # API 키 누락(config.require_*)과 DART API 오류(DartApiError)가 여기로 온다.
    # 평문 500 대신 원인을 담은 JSON을 반환해야 프론트가 사용자에게 보여줄 수 있다.
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/health")
def health():
    return {"status": "ok"}
