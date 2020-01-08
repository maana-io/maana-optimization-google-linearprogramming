FROM tiangolo/uvicorn-gunicorn:python3.7

RUN pip install ariadne uvicorn gunicorn asgi-lifespan python-dotenv requests ortools
RUN pip install ortools

COPY ./app /app