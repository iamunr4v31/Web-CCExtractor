FROM tiangolo/uvicorn-gunicorn:python3.8

ENV POETRY_VERSION=1.2.1

RUN apt-get update && apt-get upgrade -y

RUN apt-get install -y ccextractor

RUN apt-get install -y curl \
    bash \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    tesseract-ocr-eng
    # && curl -sSL https://install.python-poetry.org | python3 -

ARG FLASK_ENV="production"
ENV FLASK_ENV="${FLASK_ENV}" \
    PYTHONUNBUFFERED="true"

SHELL ["/bin/bash", "-c"]

# ENV POETRY_HOME="/opt/poetry"
# # ENV POETRY_VIRTUALENVS_IN_PROJECT=true
# ENV PATH="$POETRY_HOME/bin:$PATH"

RUN pip3 install poetry

WORKDIR /code

COPY poetry.lock pyproject.toml ./

RUN poetry config virtualenvs.create false && \
    poetry install --no-dev --no-ansi --no-root

COPY . .

CMD ["gunicorn", "-w", "4", "--threads", "4", "--bind", "0.0.0.0:8000",  "--timeout", "0", "stream_flask.app:app"]