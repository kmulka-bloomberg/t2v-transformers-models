import os
import asyncio
from logging import getLogger
from fastapi import FastAPI, Response, status
from vectorizer import Vectorizer, VectorInput
from meta import Meta
from concurrent.futures import ProcessPoolExecutor
import multiprocessing

app = FastAPI()
vec : Vectorizer
meta_config : Meta
logger = getLogger('uvicorn')



def initializer_worker():
    global vec
    global meta_config

    cuda_env = os.getenv("ENABLE_CUDA")
    cuda_support=False
    cuda_core=""

    if cuda_env is not None and cuda_env == "true" or cuda_env == "1":
        cuda_support=True
        cuda_core = os.getenv("CUDA_CORE")
        if cuda_core is None or cuda_core == "":
            cuda_core = "cuda:0"
        logger.info(f"CUDA_CORE set to {cuda_core}")
    else:
        logger.info("Running on CPU")

    meta_config = Meta('./models/model')
    vec = Vectorizer('./models/model', cuda_support, cuda_core,
                     meta_config.getModelType(), meta_config.get_architecture())

@app.on_event("startup")
def startup_event():
    global executor

    multiprocessing.set_start_method('spawn')
    initializer_worker()
    executor = ProcessPoolExecutor(initializer=initializer_worker)


@app.get("/.well-known/live", response_class=Response)
@app.get("/.well-known/ready", response_class=Response)
def live_and_ready(response: Response):
    response.status_code = status.HTTP_204_NO_CONTENT


@app.get("/meta")
def meta():
    return meta_config.get()


def vectorize(item):
    async def inner(item):
        vector = await vec.vectorize(item.text, item.config)
        return vector
    return asyncio.run(inner(item))

@app.post("/vectors")
@app.post("/vectors/")
async def read_item(item: VectorInput, response: Response):
    try:
        loop = asyncio.get_running_loop()
        vector = await loop.run_in_executor(executor, vectorize, item)
        return {"text": item.text, "vector": vector.tolist(), "dim": len(vector)}
    except Exception as e:
        logger.exception(
            'Something went wrong while vectorizing data.'
        )
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"error": str(e)}
