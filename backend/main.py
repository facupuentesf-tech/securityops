from fastapi import FastAPI


app = FastAPI(title="SecurityOps")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
