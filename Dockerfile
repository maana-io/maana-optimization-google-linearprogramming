FROM tiangolo/uvicorn-gunicorn:python3.7

RUN pip install ariadne uvicorn gunicorn asgi-lifespan python-dotenv requests graphqlclient
RUN pip install ortools

COPY ./app /app
COPY .env /.env
COPY start.sh /start.sh
WORKDIR /
